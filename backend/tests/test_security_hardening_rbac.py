import os
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Set testing environment variables
os.environ["ENVIRONMENT"] = "testing"
os.environ["DB_PATH"] = ":memory:"
os.environ["AWS_SAAS_ACCOUNT_ID"] = "123456789012"

import database
database.init_db()
from main import app
from aws_scanner import generate_cloudformation_template, generate_session_policy

client = TestClient(app)


# =====================================================================
# --- Section 1 Tests: CloudFormation Guardrails & Permissions Boundary ---
# =====================================================================

def test_tier2_cfn_template_explicit_deny_and_managedby_condition():
    """Verify Tier 2 remediation template includes explicit Deny and ManagedBy tag condition."""
    cfn_yaml = generate_cloudformation_template("123456789012", "ext_test_123", mode="remediation")
    
    # 1. Must contain explicit deny for destructive and unauthorized APIs
    assert "Sid: ExplicitDenyDestructiveActions" in cfn_yaml
    assert "ec2:TerminateInstances" in cfn_yaml
    assert "ec2:DeleteSnapshot" in cfn_yaml
    assert "ec2:DeleteVolume" in cfn_yaml
    assert "rds:DeleteDBInstance" in cfn_yaml
    assert "iam:*" in cfn_yaml
    assert "organizations:*" in cfn_yaml

    # 2. Must scope Allow actions with aws:ResourceTag/ManagedBy: CloudCostDetective
    assert "Sid: ScopedAllowRemediationActions" in cfn_yaml
    assert "aws:ResourceTag/ManagedBy" in cfn_yaml
    assert "CloudCostDetective" in cfn_yaml


def test_permissions_boundary_attached_to_all_tiers():
    """Verify PermissionsBoundary ManagedPolicy is generated and attached across all tiers."""
    for tier in ["readonly", "remediation", "admin"]:
        cfn_yaml = generate_cloudformation_template("123456789012", "ext_test_123", mode=tier)
        assert "CloudCostDetectivePermissionsBoundary:" in cfn_yaml
        assert "PermissionsBoundary: !Ref CloudCostDetectivePermissionsBoundary" in cfn_yaml
        assert "Sid: DenyDangerousOps" in cfn_yaml


def test_tier3_admin_max_duration_capped_at_90_days():
    """Verify Tier 3 Admin disallows permanent duration and enforces a maximum 90-day time lock."""
    # When duration_days is None (permanent requested), it must be capped to 90 days
    cfn_yaml_perm = generate_cloudformation_template("123456789012", "ext_test_123", mode="admin", duration_days=None)
    assert "DateLessThan:" in cfn_yaml_perm
    assert "Time-Limited: 90 Days" in cfn_yaml_perm

    # When duration_days > 90 (e.g. 365 days), it must be capped to 90 days
    cfn_yaml_long = generate_cloudformation_template("123456789012", "ext_test_123", mode="admin", duration_days=365)
    assert "Time-Limited: 90 Days" in cfn_yaml_long


# =====================================================================
# --- Section 2 Tests: Backend RBAC Enforcement (FinOps 403 checks) ---
# =====================================================================

def test_finops_token_gets_403_on_remediation_endpoint():
    """Verify a FinOps / viewer token cannot trigger remediation even with direct API requests."""
    from main import get_current_user
    # Create finops user profile in DB
    database.get_or_create_user_profile("user_finops_01", "finops_analyst@company.com", default_role="finops")
    
    app.dependency_overrides[get_current_user] = lambda: {
        "user": {"id": "user_finops_01", "email": "finops_analyst@company.com", "role": "finops"},
        "token": "test-finops-token"
    }

    try:
        response = client.post(
            "/api/remediate",
            json={
                "analysis_id": "anl_test_01",
                "resource_id": "i-0123456789abcdef0",
                "issue_type": "ec2_idle",
                "region": "us-east-1"
            }
        )
        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "INSUFFICIENT_PERMISSIONS"
    finally:
        app.dependency_overrides.clear()


def test_finops_token_gets_403_on_quarantine_endpoints():
    """Verify a FinOps role cannot apply or dismiss quarantine."""
    from main import get_current_user
    database.get_or_create_user_profile("user_finops_02", "viewer@company.com", default_role="finops")
    
    app.dependency_overrides[get_current_user] = lambda: {
        "user": {"id": "user_finops_02", "email": "viewer@company.com", "role": "finops"},
        "token": "test-token"
    }

    try:
        # Apply quarantine
        resp_apply = client.post(
            "/api/v1/quarantine/apply",
            json={
                "resource_id": "vol-12345678",
                "resource_type": "EBS Volume",
                "region": "us-east-1",
                "reason": "Unattached volume"
            }
        )
        assert resp_apply.status_code == 403

        # Safe delete
        resp_del = client.post(
            "/api/v1/quarantine/safe-delete",
            json={
                "item_id": "quar_123",
                "resource_id": "vol-12345678",
                "region": "us-east-1"
            }
        )
        assert resp_del.status_code == 403
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# --- Section 3 Tests: Org-Binding & Confused-Deputy Prevention ---
# =====================================================================

def test_org_binding_flow():
    """Test full org-binding flow: initial admin bind, cross-org takeover rejection, non-admin rejection."""
    role_arn_target = "arn:aws:iam::999888777666:role/TargetCloudRole"
    
    # (c) Non-admin in Org A attempting initial binding -> REJECTED
    passed, msg, acc = database.check_and_bind_account(
        org_id="org_alpha",
        user_id="user_devops_alpha",
        user_role="devops",
        account_alias="Alpha-Dev",
        aws_account_id="999888777666",
        role_arn=role_arn_target,
        external_id="ext_alpha_123"
    )
    assert passed is False
    assert "Only an Organization Admin" in msg

    # (a) Org Admin in Org A binding for the first time -> SUCCESS
    passed, msg, acc = database.check_and_bind_account(
        org_id="org_alpha",
        user_id="user_admin_alpha",
        user_role="admin",
        account_alias="Alpha-Prod",
        aws_account_id="999888777666",
        role_arn=role_arn_target,
        external_id="ext_alpha_123"
    )
    assert passed is True
    assert acc is not None
    assert acc["org_id"] == "org_alpha"

    # (b) User from Org B attempting to bind the SAME Role ARN -> REJECTED (Confused-Deputy Defense)
    passed, msg, acc = database.check_and_bind_account(
        org_id="org_bravo_attacker",
        user_id="user_admin_bravo",
        user_role="admin",
        account_alias="Stolen-Role",
        aws_account_id="999888777666",
        role_arn=role_arn_target,
        external_id="ext_bravo_456"
    )
    assert passed is False
    # Error message must be generic and not leak existence
    assert "Unable to verify and bind this AWS Role" in msg

    # Verify security audit event was recorded for the takeover attempt
    events = database.get_security_events()
    assert any(e["event_type"] == "CROSS_ORG_ACCOUNT_TAKEOVER_ATTEMPT" for e in events)


# =====================================================================
# --- Section 4 Tests: Identity, Domain Challenge & Role Promotion ---
# =====================================================================

def test_domain_challenge_and_role_promotion():
    """Test domain DNS TXT challenge, domain verification, and role promotion audit trail."""
    org_id = "acmecorp.com"
    
    # 1. Request domain challenge token
    token = database.create_org_domain_challenge(org_id, "acmecorp.com")
    assert token.startswith("cloudcost-verify-")

    # 2. Verify domain challenge with valid token
    success = database.verify_org_domain(org_id, "acmecorp.com", token, "admin_claimant_01")
    assert success is True

    # 3. New user signs up under matching domain -> auto-joins as finops (least privilege)
    new_user = database.get_or_create_user_profile("user_bob", "bob@acmecorp.com", org_id=org_id)
    assert new_user["role"] == "finops"

    # 4. Admin promotes user from finops to devops
    promoted = database.update_user_role_db(
        user_id="user_bob",
        new_role="devops",
        promoted_by_user_id="admin_claimant_01",
        org_id=org_id,
        reason="Promoted to DevOps lead"
    )
    assert promoted is True

    # Check updated profile
    updated_profile = database.get_user_profile_db("user_bob")
    assert updated_profile["role"] == "devops"


# =====================================================================
# --- Section 5 Tests: Session Policy & Dual-Control Approvals ---
# =====================================================================

def test_session_policy_generation():
    """Verify session policies restrict actions and resources according to least privilege."""
    policy_json = generate_session_policy("remediation", ["arn:aws:ec2:us-east-1:123456789012:instance/i-12345"])
    policy = json.loads(policy_json)
    
    assert policy["Version"] == "2012-10-17"
    statements = policy["Statement"]
    allow_stmt = next(s for s in statements if s["Effect"] == "Allow")
    assert "ec2:StopInstances" in allow_stmt["Action"]
    assert "arn:aws:ec2:us-east-1:123456789012:instance/i-12345" in allow_stmt["Resource"]

    deny_stmt = next(s for s in statements if s["Effect"] == "Deny")
    assert "ec2:TerminateInstances" in deny_stmt["Action"]


def test_dual_control_remediation_approval_workflow():
    """Verify dual-control approval prevents self-approval and enforces second reviewer approval."""
    org_id = "test_org_dual"
    
    # 1. Create approval request
    req = database.create_remediation_approval(
        org_id=org_id,
        requester_id="devops_alice",
        requester_email="alice@company.com",
        action="ec2:StopInstances",
        resource_id="i-prod-database-01",
        resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-prod-database-01",
        environment="Production",
        reason="Idle production replica"
    )
    assert req["status"] == "pending"

    # 2. Requester attempting to self-approve -> MUST RAISE ERROR (Dual-Control Enforced)
    with pytest.raises(ValueError) as exc:
        database.review_remediation_approval(
            approval_id=req["id"],
            approver_id="devops_alice",
            approver_email="alice@company.com",
            decision="approved",
            org_id=org_id
        )
    assert "Dual-control violation" in str(exc.value)

    # 3. Second reviewer (Admin or Peer DevOps) approves -> SUCCESS
    approved_req = database.review_remediation_approval(
        approval_id=req["id"],
        approver_id="admin_charlie",
        approver_email="charlie@company.com",
        decision="approved",
        org_id=org_id
    )
    assert approved_req["status"] == "approved"
    assert approved_req["approver_id"] == "admin_charlie"


# =====================================================================
# --- Section 6 Tests: Immutable Activity Audit Trail ---
# =====================================================================

def test_activity_audit_logs():
    """Verify all actions are logged and readable by org admins."""
    org_id = "test_org_audit"
    
    database.log_activity_event(
        user_id="user_admin_01",
        user_email="admin@company.com",
        org_id=org_id,
        action="CONNECT_CLOUD_ACCOUNT",
        target_arn="arn:aws:iam::123456789012:role/AuditRole",
        tier="readonly",
        result="success",
        details={"status": "connected"}
    )

    logs = database.get_activity_logs(org_id)
    assert len(logs) >= 1
    assert logs[0]["action"] == "CONNECT_CLOUD_ACCOUNT"
    assert logs[0]["user_email"] == "admin@company.com"

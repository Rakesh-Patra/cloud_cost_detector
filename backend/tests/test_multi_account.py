from unittest.mock import patch, MagicMock
import database
from aws_scanner import generate_cloudformation_template

def test_generate_cloudformation_template():
    tmpl = generate_cloudformation_template("123456789012", "ext_test_12345")
    assert "CloudCostDetective-AuditRole" in tmpl
    assert "sts:ExternalId" in tmpl
    assert "ext_test_12345" in tmpl
    assert "arn:aws:iam::" in tmpl

def test_cloud_account_db_crud():
    acc = database.save_cloud_account(
        account_id="acc_test_1",
        org_id="default_org",
        account_alias="Production-Main",
        aws_account_id="112233445566",
        role_arn="arn:aws:iam::112233445566:role/CostAuditRole",
        external_id="ext_secret_token",
        regions=["us-east-1", "us-west-2"]
    )
    assert acc["id"] == "acc_test_1"
    assert acc["account_alias"] == "Production-Main"

    # List
    accounts = database.list_cloud_accounts("default_org")
    assert len(accounts) >= 1
    assert accounts[0]["aws_account_id"] == "112233445566"

    # Get
    fetched = database.get_cloud_account("acc_test_1", "default_org")
    assert fetched is not None
    assert fetched["role_arn"] == "arn:aws:iam::112233445566:role/CostAuditRole"

    # Delete
    deleted = database.delete_cloud_account("acc_test_1", "default_org")
    assert deleted is True
    assert database.get_cloud_account("acc_test_1", "default_org") is None

def test_accounts_api_endpoints(client):
    # Get CFN template
    resp = client.get("/api/v1/accounts/cfn-template")
    assert resp.status_code == 200
    data = resp.json()
    assert "cfn_yaml" in data
    assert "quick_create_url" in data
    assert "external_id" in data

    # Connect account
    with patch("boto3.client") as mock_boto:
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIA_TEST",
                "SecretAccessKey": "SECRET_TEST",
                "SessionToken": "TOKEN_TEST"
            }
        }
        mock_sts.get_caller_identity.return_value = {"Arn": "arn:aws:sts::123:assumed-role/test"}
        mock_boto.return_value = mock_sts

        conn_resp = client.post("/api/v1/accounts/connect", json={
            "account_alias": "Staging Account",
            "aws_account_id": "998877665544",
            "role_arn": "arn:aws:iam::998877665544:role/AuditRole",
            "external_id": data["external_id"],
            "regions": ["us-east-1"]
        })
        assert conn_resp.status_code == 201
        created = conn_resp.json()
        assert created["account_alias"] == "Staging Account"

        # List accounts endpoint
        list_resp = client.get("/api/v1/accounts")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["accounts"]) >= 1

def test_multi_tenant_data_isolation():
    # Setup accounts for two different orgs
    database.save_cloud_account(
        account_id="acc_org_a",
        org_id="org_alpha_123",
        account_alias="Org A Account",
        aws_account_id="111111111111",
        role_arn="arn:aws:iam::111111111111:role/AuditRole",
        external_id="ext_alpha"
    )
    database.save_cloud_account(
        account_id="acc_org_b",
        org_id="org_beta_456",
        account_alias="Org B Account",
        aws_account_id="222222222222",
        role_arn="arn:aws:iam::222222222222:role/AuditRole",
        external_id="ext_beta"
    )

    # Org Alpha only sees its own accounts
    accounts_a = database.list_cloud_accounts("org_alpha_123")
    assert len(accounts_a) == 1
    assert accounts_a[0]["id"] == "acc_org_a"
    assert accounts_a[0]["aws_account_id"] == "111111111111"

    # Org Beta only sees its own accounts
    accounts_b = database.list_cloud_accounts("org_beta_456")
    assert len(accounts_b) == 1
    assert accounts_b[0]["id"] == "acc_org_b"
    assert accounts_b[0]["aws_account_id"] == "222222222222"

    # Cross-tenant get_cloud_account must return None when org_id mismatch
    assert database.get_cloud_account("acc_org_a", "org_beta_456") is None
    assert database.get_cloud_account("acc_org_b", "org_alpha_123") is None

def test_external_id_stability_per_org(client):
    # Calling CFN template multiple times for the same org returns the exact same External ID
    resp1 = client.get("/api/v1/accounts/cfn-template")
    resp2 = client.get("/api/v1/accounts/cfn-template")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["external_id"] == resp2.json()["external_id"]
    assert resp1.json()["external_id"].startswith("ext_")

def test_cloudformation_template_tier_modes(client):
    # Tier 1 Read-Only
    tmpl_ro = generate_cloudformation_template("123456789012", "ext_123", mode="readonly")
    assert "SecurityAudit" in tmpl_ro
    assert "FinOpsActiveRemediationAccess" not in tmpl_ro
    assert "ec2:StopInstances" not in tmpl_ro

    # Tier 2 Active Remediation
    tmpl_rem = generate_cloudformation_template("123456789012", "ext_123", mode="remediation")
    assert "SecurityAudit" in tmpl_rem
    assert "FinOpsActiveRemediationAccess" in tmpl_rem
    assert "ec2:StopInstances" in tmpl_rem
    assert "ec2:CreateSnapshot" in tmpl_rem
    assert "ec2:DeleteVolume" in tmpl_rem

    # API mode parameter
    resp = client.get("/api/v1/accounts/cfn-template?mode=remediation")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "remediation"
    assert "FinOpsActiveRemediationAccess" in resp.json()["cfn_yaml"]

def test_analyze_all_multi_region_endpoint(client):
    with patch("main.scan_all_resources", return_value=[{"id": "i-test", "type": "EC2 Instance"}]), \
         patch("main.analyze_costs", return_value={"executive_summary": "Test", "recommendations": []}):
        resp = client.post("/api/analyze/all", json={
            "regions": ["us-east-1", "us-west-2"]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["regions_scanned"] == ["us-east-1", "us-west-2"]
        assert data["resources_scanned"] == 2

def test_advisory_lock_mechanism():
    acquired, conn, db_type = database.acquire_advisory_lock(99999)
    assert acquired is True
    database.release_advisory_lock(conn, db_type, 99999)

def test_time_limited_cloudformation_template(client):
    # Template with 30-day expiration
    tmpl_30d = generate_cloudformation_template("123456789012", "ext_123", mode="readonly", duration_days=30)
    assert "DateLessThan" in tmpl_30d
    assert "aws:CurrentTime" in tmpl_30d
    assert "Time-Limited: 30 Days" in tmpl_30d

    # API query with duration_days
    resp = client.get("/api/v1/accounts/cfn-template?duration_days=7")
    assert resp.status_code == 200
    assert resp.json()["duration_days"] == 7
    assert "DateLessThan" in resp.json()["cfn_yaml"]

def test_time_limited_account_expiration(client):
    # Connect account with past expiration date
    from datetime import datetime, timezone, timedelta
    past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    database.save_cloud_account(
        account_id="acc_expired_test",
        org_id="test-user-id",
        account_alias="Expired POC",
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/AuditRole",
        external_id="ext_test",
        expires_at=past_date
    )

    # list_cloud_accounts dynamically reflects 'expired'
    acc = database.get_cloud_account("acc_expired_test", "test-user-id")
    assert acc is not None
    assert acc["status"] == "expired"

    # /api/analyze must reject expired account with 403 Forbidden
    resp = client.post("/api/analyze", json={
        "region": "us-east-1",
        "account_id": "acc_expired_test"
    })
    assert resp.status_code == 403
    assert "expired" in resp.json()["detail"].lower()

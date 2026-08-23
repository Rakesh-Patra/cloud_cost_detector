from unittest.mock import MagicMock
import database
from aws_scanner import safe_delete_ebs_volume

def test_quarantine_db_crud():
    item = database.save_quarantine_item(
        item_id="quar_test_1",
        org_id="default_org",
        account_id="acc_1",
        resource_id="vol-09876",
        resource_type="EBS Volume",
        region="us-east-1",
        reason="Unattached for > 30 days",
        quarantine_days=7
    )
    assert item["id"] == "quar_test_1"
    assert item["status"] == "quarantined"
    assert "quarantine_until" in item

    # List items
    items = database.list_quarantine_items("default_org")
    assert len(items) >= 1

    # Update status
    updated = database.update_quarantine_status("quar_test_1", "restored", org_id="default_org")
    assert updated is True

def test_safe_delete_snapshot_creation():
    mock_session = MagicMock()
    mock_ec2 = MagicMock()
    mock_ec2.create_snapshot.return_value = {"SnapshotId": "snap-0123456789abcdef"}
    mock_session.client.return_value = mock_ec2

    result = safe_delete_ebs_volume(mock_session, "us-east-1", "vol-01234")
    assert result["success"] is True
    assert result["snapshot_id"] == "snap-0123456789abcdef"
    mock_ec2.create_snapshot.assert_called_once()
    mock_ec2.delete_volume.assert_called_once_with(VolumeId="vol-01234")

def test_quarantine_api_endpoints(client):
    # Apply quarantine
    apply_resp = client.post("/api/v1/quarantine/apply", json={
        "resource_id": "vol-orphan-99",
        "resource_type": "EBS Volume",
        "region": "us-east-1",
        "reason": "Detached storage volume",
        "quarantine_days": 7
    })
    assert apply_resp.status_code == 201
    quar_data = apply_resp.json()
    item_id = quar_data["id"]

    # List quarantine items
    list_resp = client.get("/api/v1/quarantine/items")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) >= 1

    # Dismiss quarantine (whitelist)
    dismiss_resp = client.post("/api/v1/quarantine/dismiss", json={
        "item_id": item_id,
        "resource_id": "vol-orphan-99",
        "region": "us-east-1"
    })
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["success"] is True

def test_quarantine_and_remediate_account_validation(client):
    # 1. Invalid account_id must return 404 Not Found
    apply_resp = client.post("/api/v1/quarantine/apply", json={
        "resource_id": "vol-orphan-99",
        "resource_type": "EBS Volume",
        "region": "us-east-1",
        "reason": "Test",
        "account_id": "acc_nonexistent_123"
    })
    assert apply_resp.status_code == 404
    assert "not found" in apply_resp.json()["detail"].lower()

    dismiss_resp = client.post("/api/v1/quarantine/dismiss", json={
        "item_id": "quar_123",
        "resource_id": "vol-orphan-99",
        "region": "us-east-1",
        "account_id": "acc_nonexistent_123"
    })
    assert dismiss_resp.status_code == 404

    safe_del_resp = client.post("/api/v1/quarantine/safe-delete", json={
        "item_id": "quar_123",
        "resource_id": "vol-orphan-99",
        "region": "us-east-1",
        "account_id": "acc_nonexistent_123"
    })
    assert safe_del_resp.status_code == 404

    remediate_resp = client.post("/api/remediate", json={
        "analysis_id": "analysis_123",
        "resource_id": "vol-orphan-99",
        "issue_type": "Unattached EBS Volume",
        "region": "us-east-1",
        "account_id": "acc_nonexistent_123"
    })
    assert remediate_resp.status_code == 404

    # 2. Expired account_id must return 403 Forbidden
    from datetime import datetime, timezone, timedelta
    past_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    database.save_cloud_account(
        account_id="acc_quar_expired",
        org_id="test-user-id",
        account_alias="Expired Account",
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/AuditRole",
        external_id="ext_test",
        expires_at=past_date
    )

    apply_exp = client.post("/api/v1/quarantine/apply", json={
        "resource_id": "vol-orphan-99",
        "resource_type": "EBS Volume",
        "region": "us-east-1",
        "reason": "Test",
        "account_id": "acc_quar_expired"
    })
    assert apply_exp.status_code == 403
    assert "expired" in apply_exp.json()["detail"].lower()

    remediate_exp = client.post("/api/remediate", json={
        "analysis_id": "analysis_123",
        "resource_id": "vol-orphan-99",
        "issue_type": "Unattached EBS Volume",
        "region": "us-east-1",
        "account_id": "acc_quar_expired"
    })
    assert remediate_exp.status_code == 403

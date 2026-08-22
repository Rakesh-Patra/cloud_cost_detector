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

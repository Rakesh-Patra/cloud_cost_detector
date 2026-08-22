import pytest
from unittest.mock import patch, AsyncMock
from fastapi import status

# Test regions endpoint with active authentication dependency override (fixture client)
def test_get_regions_authenticated(client):
    with patch("main.list_aws_regions") as mock_list_regions:
        mock_list_regions.return_value = ["us-east-1", "us-west-2"]
        response = client.get("/api/regions")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"regions": ["us-east-1", "us-west-2"]}
        mock_list_regions.assert_called_once()

# Test regions endpoint with no auth token (development default)
def test_get_regions_unauthenticated():
    from fastapi.testclient import TestClient
    from main import app
    # Create client without auth override in default/dev environment
    with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
        local_client = TestClient(app)
        response = local_client.get("/api/regions")
        # Falls back to guest user in dev and returns 200 OK
        assert response.status_code == status.HTTP_200_OK

# Test fail-closed authentication in production
def test_production_fail_closed_unauthenticated():
    from fastapi.testclient import TestClient
    from main import app
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
        local_client = TestClient(app)
        response = local_client.get("/api/regions")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"]["error"] == "AUTHENTICATION_REQUIRED"

def test_production_fail_closed_invalid_token():
    from fastapi.testclient import TestClient
    import httpx
    from main import app
    
    mock_resp = httpx.Response(status_code=401, json={"error": "invalid_grant"})
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}), \
         patch("httpx.AsyncClient.get", return_value=mock_resp):
        local_client = TestClient(app)
        response = local_client.get("/api/regions", headers={"Authorization": "Bearer bad-expired-token"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"]["error"] == "INVALID_SESSION"

def test_production_fail_closed_auth_service_error():
    from fastapi.testclient import TestClient
    import httpx
    from main import app
    
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}), \
         patch("httpx.AsyncClient.get", side_effect=httpx.RequestError("Connection timed out")):
        local_client = TestClient(app)
        response = local_client.get("/api/regions", headers={"Authorization": "Bearer any-token"})
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.json()["detail"]["error"] == "AUTH_SERVICE_UNAVAILABLE"

def test_production_authenticated_success():
    from fastapi.testclient import TestClient
    import httpx
    from main import app
    
    mock_resp = httpx.Response(status_code=200, json={"user": {"id": "usr-1", "email": "admin@prod.com"}})
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}), \
         patch("httpx.AsyncClient.get", return_value=mock_resp), \
         patch("main.list_aws_regions", return_value=["us-east-1"]):
        local_client = TestClient(app)
        response = local_client.get("/api/regions", headers={"Authorization": "Bearer valid-prod-token"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"regions": ["us-east-1"]}

# Test WebSocket connection authentication
def test_websocket_progress_unauthenticated():
    from fastapi.testclient import TestClient
    from fastapi.websockets import WebSocketDisconnect
    from main import app
    local_client = TestClient(app)
    
    # Try connecting without a token - should close connection with WS_1008_POLICY_VIOLATION
    with local_client.websocket_connect("/ws/progress/test-analysis-id") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION

@patch("main.db_client")
def test_get_history(mock_db_client, client):
    # Mock database history response
    mock_history = [
        {"id": "ana-1", "region": "us-east-1", "status": "completed", "created_at": "2026-07-10T12:00:00Z"}
    ]
    mock_db_client.get_analysis_history = AsyncMock(return_value=mock_history)
    
    response = client.get("/api/history")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_history
    mock_db_client.get_analysis_history.assert_called_once_with(token="mock-jwt-token")

@patch("main.db_client")
@patch("main.scan_all_resources")
@patch("main.analyze_costs")
@patch("main.manager.broadcast", new_callable=AsyncMock)
def test_analyze_region(mock_broadcast, mock_analyze_costs, mock_scan, mock_db_client, client):
    # Mock scanning & AI analysis
    mock_scan.return_value = [{"id": "vol-123", "type": "EBS Volume"}]
    mock_analyze_costs.return_value = {
        "executive_summary": "Summary text",
        "recommendations": [
            {"resource_id": "vol-123", "issue_type": "Unattached EBS Volume", "severity": "high", "estimated_savings": 20.0, "remediation_command": "aws ec2..."}
        ]
    }
    
    # Mock database responses
    mock_db_client.create_analysis = AsyncMock()
    mock_db_client.update_analysis_success = AsyncMock()
    
    payload = {"region": "us-east-1", "analysis_id": "ana-123"}
    response = client.post("/api/analyze", json=payload)
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["analysis_id"] == "ana-123"
    assert data["region"] == "us-east-1"
    assert len(data["resources"]) == 1
    assert data["count"] == 1
    
    # Verify sequence of database writes and progress broadcasts
    mock_db_client.create_analysis.assert_called_once_with("ana-123", "us-east-1", token="mock-jwt-token")
    mock_scan.assert_called_once_with("us-east-1")
    mock_analyze_costs.assert_called_once()
    mock_db_client.update_analysis_success.assert_called_once()
    assert mock_broadcast.call_count >= 4

@patch("main.db_client")
@patch("main.execute_remediation")
def test_remediate_resource_success(mock_remediate, mock_db_client, client):
    # Mock remediation action
    mock_remediate.return_value = {"success": True, "message": "Deleted volume."}
    
    # Mock database retrieval & patch updates
    mock_db_client.get_analysis = AsyncMock(return_value={
        "id": "ana-1",
        "analysis_result": {
            "recommendations": [
                {"resource_id": "vol-123", "issue_type": "Unattached EBS Volume", "remediated": False}
            ]
        }
    })
    mock_db_client.update_analysis_result = AsyncMock()
    
    payload = {
        "analysis_id": "ana-1",
        "resource_id": "vol-123",
        "issue_type": "Unattached EBS Volume",
        "region": "us-east-1"
    }
    response = client.post("/api/remediate", json=payload)
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["resource_id"] == "vol-123"
    
    mock_remediate.assert_called_once_with("us-east-1", "vol-123", "Unattached EBS Volume")
    mock_db_client.get_analysis.assert_called_once_with("ana-1", token="mock-jwt-token")
    mock_db_client.update_analysis_result.assert_called_once()

@patch("main.db_client")
@patch("main.execute_remediation")
def test_remediate_resource_insforge_resilience(mock_remediate, mock_db_client, client):
    # If InsForge DB throws an error, remediation still succeeds on AWS without 500 error
    mock_remediate.return_value = {"success": True, "message": "Stopped instance."}
    mock_db_client.get_analysis = AsyncMock(side_effect=Exception("401 Unauthorized: Invalid token"))
    
    payload = {
        "analysis_id": "ana-1",
        "resource_id": "i-073b03ab08242a894",
        "issue_type": "Severely idle instance",
        "region": "us-east-1"
    }
    response = client.post("/api/remediate", json=payload)
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["resource_id"] == "i-073b03ab08242a894"
    assert "remediated_at" in data

@patch("main.db_client")
def test_get_budgets(mock_db_client, client):
    mock_db_client.get_budget = AsyncMock(return_value={"threshold": 500.0, "emails": ["user@test.com"]})
    mock_db_client.get_alert_history = AsyncMock(return_value=[])
    
    response = client.get("/api/budgets")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["config"]["threshold"] == 500.0
    assert data["config"]["emails"] == ["user@test.com"]
    mock_db_client.get_budget.assert_called_once_with("test-user-id", token="mock-jwt-token")
    mock_db_client.get_alert_history.assert_called_once_with("test-user-id", token="mock-jwt-token")

@patch("main.db_client")
def test_update_budgets(mock_db_client, client):
    mock_db_client.save_budget = AsyncMock()
    
    payload = {"threshold": 1200.0, "emails": ["alert@test.com"]}
    response = client.post("/api/budgets", json=payload)
    
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"success": True, "message": "Budget configuration updated successfully."}
    mock_db_client.save_budget.assert_called_once_with(
        user_id="test-user-id",
        threshold=1200.0,
        slack_webhooks=[],
        emails=["alert@test.com"],
        token="mock-jwt-token"
    )

def test_rbac_viewer_blocked_from_remediate():
    from fastapi.testclient import TestClient
    from main import app, get_current_user
    
    # Simulate a Viewer user
    app.dependency_overrides[get_current_user] = lambda: {
        "user": {"id": "viewer-1", "email": "viewer@company.com", "role": "viewer"},
        "token": "viewer-jwt-token"
    }
    
    with TestClient(app) as test_client:
        payload = {
            "analysis_id": "ana-1",
            "resource_id": "vol-123",
            "issue_type": "Unattached EBS Volume",
            "region": "us-east-1"
        }
        response = test_client.post("/api/remediate", json=payload)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"]["error"] == "INSUFFICIENT_PERMISSIONS"
        
        # Verify Viewer CAN access read-only /api/me
        me_resp = test_client.get("/api/me")
        assert me_resp.status_code == status.HTTP_200_OK
        assert me_resp.json()["role"] == "viewer"
    
    app.dependency_overrides.clear()

def test_rbac_devops_can_remediate():
    from fastapi.testclient import TestClient
    from main import app, get_current_user
    
    app.dependency_overrides[get_current_user] = lambda: {
        "user": {"id": "devops-1", "email": "devops@company.com", "role": "devops"},
        "token": "devops-jwt-token"
    }
    
    with patch("main.execute_remediation", return_value={"success": True, "message": "Stopped."}), \
         patch("main.db_client.get_analysis", new_callable=AsyncMock, return_value={"analysis_result": {"recommendations": []}}), \
         patch("main.db_client.update_analysis_result", new_callable=AsyncMock):
        with TestClient(app) as test_client:
            payload = {
                "analysis_id": "ana-1",
                "resource_id": "i-12345",
                "issue_type": "Idle EC2 Instance",
                "region": "us-east-1"
            }
            response = test_client.post("/api/remediate", json=payload)
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["success"] is True
            
            # DevOps cannot connect cloud account (Admin only)
            conn_resp = test_client.post("/api/v1/accounts/connect", json={
                "account_alias": "Test", "aws_account_id": "123456789012",
                "role_arn": "arn:aws:iam::123456789012:role/test", "external_id": "ext_123"
            })
            assert conn_resp.status_code == status.HTTP_403_FORBIDDEN
            
    app.dependency_overrides.clear()

def test_rbac_production_fail_safe_defaults_to_viewer(monkeypatch):
    """Verify that in production mode, users without explicit JWT roles are strictly locked down to viewer."""
    from fastapi.testclient import TestClient
    from main import app, get_current_user
    
    monkeypatch.setenv("ENVIRONMENT", "production")
    
    # User with 'admin' in email but NO verified role in DB/JWT
    app.dependency_overrides[get_current_user] = lambda: {
        "user": {"id": "user-999", "email": "fake-admin@random.com"},
        "token": "valid-jwt-token"
    }
    
    with TestClient(app) as test_client:
        me_resp = test_client.get("/api/me")
        assert me_resp.status_code == status.HTTP_200_OK
        # Must be locked down to viewer (email matching ignored in prod)
        assert me_resp.json()["role"] == "viewer"
        
        # Must be blocked from remediations
        rem_resp = test_client.post("/api/remediate", json={
            "analysis_id": "a1", "resource_id": "i-123", "issue_type": "Idle", "region": "us-east-1"
        })
        assert rem_resp.status_code == status.HTTP_403_FORBIDDEN
        
    app.dependency_overrides.clear()

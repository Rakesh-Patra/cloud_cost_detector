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

# Test regions endpoint with no auth token
def test_get_regions_unauthenticated():
    from fastapi.testclient import TestClient
    from main import app
    # Create client without auth override
    local_client = TestClient(app)
    response = local_client.get("/api/regions")
    # Should get 403 or 401 because get_current_user requires Header
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY # Missing Header

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

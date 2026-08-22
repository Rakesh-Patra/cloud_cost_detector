from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
from ai_analyzer import AICircuitBreaker, estimate_tokens, log_ai_usage

def test_ai_circuit_breaker_transition():
    cb = AICircuitBreaker(failure_threshold=3, recovery_timeout_seconds=0.1)
    assert cb.state == "CLOSED"
    assert cb.can_attempt() is True

    # Record 2 failures -> stays CLOSED
    cb.record_failure(Exception("Fail 1"))
    cb.record_failure(Exception("Fail 2"))
    assert cb.state == "CLOSED"
    assert cb.can_attempt() is True

    # 3rd failure -> trips to OPEN
    cb.record_failure(Exception("Fail 3"))
    assert cb.state == "OPEN"
    assert cb.can_attempt() is False

    # After recovery timeout -> HALF-OPEN
    import time
    time.sleep(0.15)
    assert cb.can_attempt() is True
    assert cb.state == "HALF-OPEN"

    # Success closes circuit
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0

def test_token_estimation_and_usage_logging():
    prompt = "This is a prompt for cloud cost analysis."
    tokens = estimate_tokens(prompt)
    assert tokens > 0
    # Should not throw any exception
    log_ai_usage(len(prompt), "Here is the cost analysis summary.")

def test_x_api_key_authentication():
    test_key = "test-api-key-for-unit-tests-only"  # nosec - not a real secret
    with patch.dict("os.environ", {"API_SECRET_KEY": test_key, "ENVIRONMENT": "production"}):
        local_client = TestClient(app)
        # Test with valid X-API-Key
        response = local_client.get("/api/regions", headers={"X-API-Key": test_key})
        assert response.status_code == 200

        # Test with invalid X-API-Key
        bad_resp = local_client.get("/api/regions", headers={"X-API-Key": "wrong-key"})
        assert bad_resp.status_code == 401

def test_rate_limiting_configured():
    # Verify limiter is attached to app state
    assert hasattr(app.state, "limiter")
    assert app.state.limiter is not None

def test_readiness_probe(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

def test_liveness_probe(client):
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "timestamp" in response.json()

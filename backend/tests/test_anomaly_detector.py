import pytest
from unittest.mock import patch
from anomaly_detector import detect_cost_anomalies, send_alert, send_email_alert

def test_detect_cost_anomalies_insufficient_data():
    # Less than 8 days should return no anomalies
    daily_costs = [{"date": f"2026-07-0{i}", "amount": 10.0} for i in range(1, 7)]
    anomalies = detect_cost_anomalies(daily_costs)
    assert len(anomalies) == 0

def test_detect_cost_anomalies_stable_costs():
    # Constant spend should have no anomalies
    daily_costs = [{"date": f"2026-07-{str(i).zfill(2)}", "amount": 100.0} for i in range(1, 10)]
    anomalies = detect_cost_anomalies(daily_costs)
    assert len(anomalies) == 0

def test_detect_cost_anomalies_with_spike():
    # 7 days of 10.0 spend, then 25.0 spend (spike of 150% over rolling average 10.0, difference is 15.0 > 5.0)
    daily_costs = [{"date": f"2026-07-{str(i).zfill(2)}", "amount": 10.0} for i in range(1, 8)]
    daily_costs.append({"date": "2026-07-08", "amount": 25.0})
    
    anomalies = detect_cost_anomalies(daily_costs)
    assert len(anomalies) == 1
    assert anomalies[0]["date"] == "2026-07-08"
    assert anomalies[0]["amount"] == 25.0
    assert anomalies[0]["average"] == 10.0
    assert anomalies[0]["percent_increase"] == 150.0

def test_detect_cost_anomalies_under_noise_threshold():
    # Cost spike but under $5 noise threshold
    daily_costs = [{"date": f"2026-07-{str(i).zfill(2)}", "amount": 1.0} for i in range(1, 8)]
    daily_costs.append({"date": "2026-07-08", "amount": 3.0}) # 200% spike, but amount is $3 (<= $5.0)
    
    anomalies = detect_cost_anomalies(daily_costs)
    assert len(anomalies) == 0

@pytest.mark.asyncio
@patch("anomaly_detector.send_email_alert")
async def test_send_alert_email_routing(mock_send_email):
    mock_send_email.return_value = True
    anomaly = {"date": "2026-07-08", "amount": 150.0, "average": 100.0, "percent_increase": 50.0}
    channels = ["rakesh@example.com", "invalid-channel"]
    
    notified = await send_alert(anomaly, channels)
    # Only email should be triggered, and invalid-channel should be ignored
    assert len(notified) == 1
    assert notified[0] == "Email: rakesh@example.com"
    mock_send_email.assert_called_once_with("rakesh@example.com", anomaly, is_test=False, is_simulated=False)

@pytest.mark.asyncio
@patch("os.environ.get")
@patch("anomaly_detector._send_via_smtp")
async def test_send_email_alert_via_gmail_smtp(mock_send_smtp, mock_env_get):
    # Mock environment to select Gmail SMTP
    mock_env = {
        "GMAIL_USER": "test@gmail.com",
        "GMAIL_APP_PASSWORD": "app-password"
    }
    mock_env_get.side_effect = lambda key, default=None: mock_env.get(key, default)
    
    anomaly = {"date": "2026-07-08", "amount": 150.0, "average": 100.0, "percent_increase": 50.0}
    
    result = await send_email_alert("user@example.com", anomaly)
    assert result is True
    mock_send_smtp.assert_called_once()
    args, kwargs = mock_send_smtp.call_args
    assert kwargs["host"] == "smtp.gmail.com"
    assert kwargs["username"] == "test@gmail.com"
    assert kwargs["to"] == "user@example.com"

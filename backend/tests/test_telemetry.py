from unittest.mock import MagicMock
from pricing_engine import PricingEngine
from aws_scanner import get_instance_metric_telemetry
from ai_analyzer import _deterministic_pre_filter

def test_pricing_engine_calculations():
    # EC2 Monthly Cost
    ec2_cost = PricingEngine.get_ec2_monthly_cost("t3.medium", "us-east-1")
    assert ec2_cost > 0
    assert ec2_cost == round(0.0416 * 730.0, 2)

    # EBS gp2 vs gp3 Savings
    savings = PricingEngine.calculate_gp2_to_gp3_savings(size_gb=100)
    # gp2 = $10, gp3 = $8, delta = $2
    assert savings == 2.0

    # Unattached EBS Volume Waste Evaluation
    unattached_vol = {
        "id": "vol-012345",
        "type": "EBS Volume",
        "state": "available",
        "configuration": {"size_gb": 50, "volume_type": "gp2"}
    }
    eval_res = PricingEngine.evaluate_resource_waste(unattached_vol, "us-east-1")
    assert eval_res["is_wasteful"] is True
    assert eval_res["recommendation_type"] == "UNATTACHED_EBS"
    assert eval_res["monthly_waste_dollars"] == 5.0 # 50 * 0.10

def test_telemetry_metric_ingestion():
    mock_session = MagicMock()
    mock_cw = MagicMock()
    mock_cw.get_metric_data.return_value = {
        "MetricDataResults": [
            {
                "Id": "cpu_util",
                "Values": [0.4, 0.6, 0.8, 1.2, 0.5, 0.3]
            }
        ]
    }
    mock_session.client.return_value = mock_cw

    telemetry = get_instance_metric_telemetry(mock_session, "us-east-1", "i-test1234", days=14)
    assert telemetry["avg_cpu_percent"] < 2.0
    assert "Definite Idle" in telemetry["workload_classification"]

def test_deterministic_pre_filtering():
    resources = [
        # Wasteful unattached volume
        {
            "id": "vol-unattached",
            "type": "EBS Volume",
            "state": "available",
            "configuration": {"size_gb": 100, "volume_type": "gp2"}
        },
        # gp2 upgrade candidate
        {
            "id": "vol-gp2",
            "type": "EBS Volume",
            "state": "in-use",
            "configuration": {"size_gb": 200, "volume_type": "gp2"}
        },
        # Healthy modern gp3 volume
        {
            "id": "vol-healthy",
            "type": "EBS Volume",
            "state": "in-use",
            "configuration": {"size_gb": 50, "volume_type": "gp3"}
        }
    ]

    flagged, total_waste = _deterministic_pre_filter(resources, "us-east-1")
    assert len(flagged) == 2
    assert total_waste == 14.0 # (100 * $0.10 = $10) + (200 * $0.02 savings = $4)
    assert flagged[0]["resource_id"] == "vol-unattached"
    assert "delete-volume" in flagged[0]["remediation_command"]

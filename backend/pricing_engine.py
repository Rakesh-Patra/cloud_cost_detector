"""
AWS Pricing Engine for Cloud Cost Detective.
Provides precision cost calculation, regional rate lookup, and savings delta calculation.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger("pricing_engine")

# Base Regional Rates (Hourly On-Demand for standard Linux instances, USD)
EC2_ON_DEMAND_HOURLY: Dict[str, float] = {
    # General Purpose
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "t4g.nano": 0.0042,
    "t4g.micro": 0.0084,
    "t4g.small": 0.0168,
    "t4g.medium": 0.0336,
    "t4g.large": 0.0672,
    "t4g.xlarge": 0.1344,
    "t4g.2xlarge": 0.2688,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768,
    "m6i.large": 0.096,
    "m6i.xlarge": 0.192,
    "m6i.2xlarge": 0.384,
    # Compute Optimized
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "c5.2xlarge": 0.34,
    "c6i.large": 0.085,
    "c6i.xlarge": 0.17,
    # Memory Optimized
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
}

# Regional EBS Monthly Cost per GB (USD)
EBS_STORAGE_MONTHLY_PER_GB: Dict[str, float] = {
    "standard": 0.05,
    "gp2": 0.10,
    "gp3": 0.08,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
}

# RDS Base Rates (Hourly Single-AZ, USD)
RDS_HOURLY: Dict[str, float] = {
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
    "db.t4g.micro": 0.015,
    "db.t4g.small": 0.030,
    "db.t4g.medium": 0.060,
    "db.m5.large": 0.178,
    "db.m5.xlarge": 0.356,
    "db.r5.large": 0.24,
    "db.r5.xlarge": 0.48,
}

# Unattached Elastic IP Rate ($0.005 / hr per unallocated IP)
EIP_IDLE_HOURLY = 0.005

HOURS_PER_MONTH = 730.0

class PricingEngine:
    """Calculates exact cloud waste and modernization potential."""

    @staticmethod
    def get_ec2_monthly_cost(instance_type: str, region: str = "us-east-1") -> float:
        """Calculate monthly On-Demand running cost for an EC2 instance."""
        hourly = EC2_ON_DEMAND_HOURLY.get(instance_type.lower(), 0.096)  # fallback to m5.large average
        multiplier = 1.1 if any(r in region for r in ["eu-", "ap-", "sa-"]) else 1.0
        return round(hourly * HOURS_PER_MONTH * multiplier, 2)

    @staticmethod
    def get_ebs_monthly_cost(volume_type: str, size_gb: int, region: str = "us-east-1") -> float:
        """Calculate monthly storage cost for an EBS volume."""
        rate = EBS_STORAGE_MONTHLY_PER_GB.get(volume_type.lower(), 0.10)
        return round(rate * size_gb, 2)

    @staticmethod
    def calculate_gp2_to_gp3_savings(size_gb: int) -> float:
        """gp3 is 20% cheaper than gp2 ($0.08 vs $0.10/GB-month)."""
        gp2_cost = 0.10 * size_gb
        gp3_cost = 0.08 * size_gb
        return round(gp2_cost - gp3_cost, 2)

    @staticmethod
    def get_rds_monthly_cost(instance_class: str, is_multi_az: bool = False) -> float:
        """Calculate monthly running cost for RDS instance."""
        hourly = RDS_HOURLY.get(instance_class.lower(), 0.068)
        if is_multi_az:
            hourly *= 2.0
        return round(hourly * HOURS_PER_MONTH, 2)

    @staticmethod
    def get_idle_eip_monthly_cost() -> float:
        """Unattached Elastic IP costs $0.005/hour."""
        return round(EIP_IDLE_HOURLY * HOURS_PER_MONTH, 2)

    @classmethod
    def evaluate_resource_waste(cls, resource: Dict[str, Any], region: str = "us-east-1") -> Dict[str, Any]:
        """
        Deterministic evaluator that accurately scores waste and potential savings.
        """
        r_type = resource.get("type", "")
        waste_dollars = 0.0
        recommendation_type = "OPTIMAL"
        details = ""

        # 1. Unattached EBS Volume
        if r_type == "EBS Volume" and resource.get("state") == "available":
            size = resource.get("configuration", {}).get("size_gb", 0)
            vol_type = resource.get("configuration", {}).get("volume_type", "gp2")
            waste_dollars = cls.get_ebs_monthly_cost(vol_type, size, region)
            recommendation_type = "UNATTACHED_EBS"
            details = f"Unattached {size}GB {vol_type} volume costing ${waste_dollars}/mo with zero active I/O."

        # 2. gp2 to gp3 Upgrade candidate
        elif r_type == "EBS Volume" and resource.get("configuration", {}).get("volume_type") == "gp2":
            size = resource.get("configuration", {}).get("size_gb", 0)
            savings = cls.calculate_gp2_to_gp3_savings(size)
            if savings > 0:
                waste_dollars = savings
                recommendation_type = "MODERNIZE_GP2"
                details = f"Legacy gp2 volume ({size}GB). Upgrading to gp3 saves ${savings}/mo and boosts IOPS to 3000 baseline."

        # 3. Stopped EC2 Instance
        elif r_type == "EC2 Instance" and resource.get("state") == "stopped":
            recommendation_type = "STOPPED_EC2"
            details = "Stopped instance. Consider terminating or snapshotting to eliminate root volume storage cost."

        # 4. Underutilized / Idle Running EC2 (Telemetry-driven)
        elif r_type == "EC2 Instance" and resource.get("state") == "running":
            telemetry = resource.get("telemetry", {})
            avg_cpu = telemetry.get("avg_cpu_percent", 50.0)
            max_cpu = telemetry.get("max_cpu_percent", 50.0)
            inst_type = resource.get("size_sku", "t3.medium")
            monthly_bill = cls.get_ec2_monthly_cost(inst_type, region)

            if avg_cpu < 2.0 and max_cpu < 5.0:
                waste_dollars = monthly_bill
                recommendation_type = "IDLE_EC2"
                details = f"Severely idle instance (14-day avg CPU {avg_cpu:.1f}%, peak {max_cpu:.1f}%). Waste: ${monthly_bill}/mo."
            elif max_cpu < 15.0:
                waste_dollars = round(monthly_bill * 0.5, 2)
                recommendation_type = "DOWNSIZE_EC2"
                details = f"Over-provisioned instance (Peak CPU {max_cpu:.1f}%). Downsizing can save ~${waste_dollars}/mo."

        # 5. RDS Stopped or Idle
        elif r_type == "RDS Instance" and resource.get("state") == "stopped":
            inst_class = resource.get("size_sku", "db.t3.medium")
            waste_dollars = round(cls.get_rds_monthly_cost(inst_class) * 0.2, 2)
            recommendation_type = "STOPPED_RDS"
            details = "Stopped RDS instance. Allocate or delete automated snapshots if obsolete."

        return {
            "is_wasteful": waste_dollars > 0 or recommendation_type in ["STOPPED_EC2", "MODERNIZE_GP2", "UNATTACHED_EBS", "IDLE_EC2"],
            "recommendation_type": recommendation_type,
            "monthly_waste_dollars": waste_dollars,
            "details": details
        }

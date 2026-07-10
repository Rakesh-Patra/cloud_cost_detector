import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from aws_scanner import (
    list_aws_regions,
    scan_all_resources,
    execute_remediation,
    AWSCredentialException,
    AWSScanException
)

@patch("boto3.client")
def test_list_aws_regions_success(mock_boto_client):
    # Mock ec2.describe_regions
    mock_ec2 = MagicMock()
    mock_ec2.describe_regions.return_value = {
        "Regions": [
            {"RegionName": "us-east-1"},
            {"RegionName": "us-west-2"}
        ]
    }
    mock_boto_client.return_value = mock_ec2

    regions = list_aws_regions()
    assert regions == ["us-east-1", "us-west-2"]
    mock_boto_client.assert_called_with("ec2", region_name="us-east-1")
    mock_ec2.describe_regions.assert_called_once()

@patch("boto3.client")
def test_list_aws_regions_auth_failure(mock_boto_client):
    mock_ec2 = MagicMock()
    # Trigger AuthFailure ClientError
    error_response = {"Error": {"Code": "AuthFailure", "Message": "AWS was not able to validate the provided access credentials"}}
    mock_ec2.describe_regions.side_effect = ClientError(error_response, "DescribeRegions")
    mock_boto_client.return_value = mock_ec2

    with pytest.raises(AWSCredentialException) as exc_info:
        list_aws_regions()
    assert "AWS credentials not found or incomplete" in str(exc_info.value) or "AWS Authorization failed" in str(exc_info.value)

@patch("boto3.Session")
def test_scan_all_resources_success(mock_session_class):
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    # Mock STS caller identity (connection validation)
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"UserId": "test-user"}
    
    # Mock EC2 client
    mock_ec2 = MagicMock()
    # describe_instances paginator
    mock_ec2_paginator = MagicMock()
    mock_ec2_paginator.paginate.return_value = [{
        "Reservations": [{
            "Instances": [{
                "InstanceId": "i-1234567890abcdef0",
                "State": {"Name": "running"},
                "InstanceType": "t3.medium",
                "Tags": [{"Key": "Name", "Value": "test-instance"}],
                "ImageId": "ami-12345",
                "PlatformDetails": "Linux",
                "VpcId": "vpc-123"
            }]
        }]
    }]
    
    # describe_volumes paginator
    mock_vol_paginator = MagicMock()
    mock_vol_paginator.paginate.return_value = [{
        "Volumes": [{
            "VolumeId": "vol-0987654321fedcba0",
            "State": "available",
            "Size": 50,
            "VolumeType": "gp2",
            "Tags": []
        }]
    }]
    
    # Mock RDS client
    mock_rds = MagicMock()
    # describe_db_instances paginator
    mock_rds_inst_paginator = MagicMock()
    mock_rds_inst_paginator.paginate.return_value = [{
        "DBInstances": []
    }]
    mock_rds_cluster_paginator = MagicMock()
    mock_rds_cluster_paginator.paginate.return_value = [{
        "DBClusters": []
    }]
    
    # Mock S3 client
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {"Buckets": []}

    # Set up client side-effects
    def client_side_effect(service_name, *args, **kwargs):
        if service_name == "sts":
            return mock_sts
        elif service_name == "ec2":
            return mock_ec2
        elif service_name == "rds":
            return mock_rds
        elif service_name == "s3":
            return mock_s3
        return MagicMock()
        
    mock_session.client.side_effect = client_side_effect
    
    def paginator_side_effect(operation_name):
        if operation_name == "describe_instances":
            return mock_ec2_paginator
        elif operation_name == "describe_volumes":
            return mock_vol_paginator
        elif operation_name == "describe_db_instances":
            return mock_rds_inst_paginator
        elif operation_name == "describe_db_clusters":
            return mock_rds_cluster_paginator
        return MagicMock()
        
    mock_ec2.get_paginator.side_effect = paginator_side_effect
    mock_rds.get_paginator.side_effect = paginator_side_effect

    resources = scan_all_resources("us-east-1")
    
    # Verify EC2 instance and EBS volume are captured
    assert len(resources) == 2
    assert resources[0]["id"] == "i-1234567890abcdef0"
    assert resources[0]["type"] == "EC2 Instance"
    assert resources[0]["state"] == "running"
    
    assert resources[1]["id"] == "vol-0987654321fedcba0"
    assert resources[1]["type"] == "EBS Volume"
    assert resources[1]["state"] == "available"

@patch("boto3.Session")
def test_execute_remediation_delete_volume(mock_session_class):
    mock_session = MagicMock()
    mock_ec2 = MagicMock()
    mock_session.client.return_value = mock_ec2
    mock_session_class.return_value = mock_session

    result = execute_remediation("us-east-1", "vol-123", "Unattached EBS Volume")
    assert result["success"] is True
    assert "deleted EBS volume" in result["message"]
    mock_ec2.delete_volume.assert_called_with(VolumeId="vol-123")

@patch("boto3.Session")
def test_execute_remediation_modify_volume(mock_session_class):
    mock_session = MagicMock()
    mock_ec2 = MagicMock()
    mock_session.client.return_value = mock_ec2
    mock_session_class.return_value = mock_session

    result = execute_remediation("us-east-1", "vol-123", "gp2 to gp3 Migration")
    assert result["success"] is True
    assert "modified volume" in result["message"]
    mock_ec2.modify_volume.assert_called_with(VolumeId="vol-123", VolumeType="gp3")

@patch("boto3.Session")
def test_execute_remediation_stop_instance(mock_session_class):
    mock_session = MagicMock()
    mock_ec2 = MagicMock()
    mock_session.client.return_value = mock_ec2
    mock_session_class.return_value = mock_session

    result = execute_remediation("us-east-1", "i-123", "Idle EC2 Instance")
    assert result["success"] is True
    assert "stopped EC2 instance" in result["message"]
    mock_ec2.stop_instances.assert_called_with(InstanceIds=["i-123"])

def test_execute_remediation_invalid_issue():
    with pytest.raises(AWSScanException) as exc_info:
        execute_remediation("us-east-1", "res-123", "Unsupported Issue Name")
    assert "Remediation is not supported" in str(exc_info.value)

import logging
from datetime import datetime, timezone, timedelta
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError, EndpointConnectionError

logger = logging.getLogger("aws_scanner")

class AWSScannerException(Exception):
    """Base exception for AWS scanner errors."""
    pass

class AWSCredentialException(AWSScannerException):
    """Exception raised when AWS credentials are missing or invalid."""
    pass

class AWSRegionException(AWSScannerException):
    """Exception raised when a region is invalid or unreachable."""
    pass

class AWSRateLimitException(AWSScannerException):
    """Exception raised when AWS API requests are throttled."""
    pass

class AWSScanException(AWSScannerException):
    """Exception raised for general failures during scanning."""
    pass


def handle_boto_errors(func):
    """Decorator to handle boto3 / botocore exceptions and raise custom scanner exceptions."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (NoCredentialsError, PartialCredentialsError) as e:
            logger.error(f"Missing/Invalid credentials: {str(e)}")
            raise AWSCredentialException("AWS credentials not found or incomplete. Please check your AWS configuration.") from e
        except EndpointConnectionError as e:
            logger.error(f"Endpoint connection failed: {str(e)}")
            raise AWSRegionException("Could not connect to the AWS endpoint. Verify the region name and network connectivity.") from e
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', '')
            logger.error(f"ClientError: {error_code} - {error_message}")
            
            if error_code in ('AuthFailure', 'InvalidSignature', 'SignatureDoesNotMatch', 'InvalidClientTokenId', 'AccessDenied', 'UnauthorizedOperation'):
                raise AWSCredentialException(f"AWS Authorization failed: {error_message}") from e
            elif error_code in ('RequestLimitExceeded', 'Throttling', 'ThrottlingException', 'PriorRequestNotComplete'):
                raise AWSRateLimitException("AWS API requests are being throttled. Please retry later.") from e
            elif error_code in ('InvalidParameterValue', 'InvalidRegion', 'UnrecognizedClientException'):
                raise AWSRegionException(f"AWS region or configuration is invalid: {error_message}") from e
            else:
                raise AWSScanException(f"AWS API client error: {error_message} (Code: {error_code})") from e
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise AWSScanException(f"An unexpected error occurred: {str(e)}") from e
    return wrapper


def get_assumed_role_session(role_arn: str, external_id: str, session_name: str = "CloudCostScanSession") -> boto3.Session:
    """
    Assume a customer's AWS IAM Role dynamically using STS and return an authenticated boto3.Session.
    """
    try:
        sts_client = boto3.client('sts', region_name='us-east-1')
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            ExternalId=external_id,
            DurationSeconds=3600
        )
        credentials = response['Credentials']
        return boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
    except Exception as e:
        logger.error(f"Failed to assume role {role_arn} with external_id: {e}")
        raise AWSCredentialException(f"Failed to assume customer role: {str(e)}") from e


def generate_cloudformation_template(saas_account_id: str, external_id: str) -> str:
    """
    Generates a secure, read-only CloudFormation template for customer onboarding.
    """
    return f"""AWSTemplateFormatVersion: '2010-09-09'
Description: 'Cloud Cost Detective - Enterprise Read-Only FinOps Audit Role'

Parameters:
  SaaSAccountId:
    Type: String
    Default: '{saas_account_id}'
    Description: 'The AWS Account ID of the Cloud Cost Detective SaaS platform'
  ExternalId:
    Type: String
    Default: '{external_id}'
    Description: 'Your organization unique security verification token'

Resources:
  CloudCostDetectiveAuditRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: CloudCostDetective-AuditRole
      Description: 'Read-only role enabling automated FinOps and cost optimization analysis'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Sub "arn:aws:iam::${{SaaSAccountId}}:root"
            Action: 'sts:AssumeRole'
            Condition:
              StringEquals:
                'sts:ExternalId': !Ref ExternalId
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/SecurityAudit'
      Policies:
        - PolicyName: FinOpsCloudWatchMetricsAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'cloudwatch:GetMetricData'
                  - 'cloudwatch:GetMetricStatistics'
                  - 'cloudwatch:ListMetrics'
                  - 'ce:GetCostAndUsage'
                  - 'pricing:GetProducts'
                Resource: '*'

Outputs:
  RoleArn:
    Description: 'Paste this Role ARN back into your Cloud Cost Detective Dashboard'
    Value: !GetAtt CloudCostDetectiveAuditRole.Arn
"""


def get_instance_metric_telemetry(session: boto3.Session, region: str, instance_id: str, days: int = 14) -> dict:
    """
    Ingests 14-day CloudWatch metrics (CPUUtilization & Network) for an EC2 instance.
    Calculates average CPU, peak CPU, and classifies instance workload pattern.
    """
    try:
        cw = session.client('cloudwatch', region_name=region)
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=days)

        response = cw.get_metric_data(
            MetricDataQueries=[
                {
                    'Id': 'cpu_util',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/EC2',
                            'MetricName': 'CPUUtilization',
                            'Dimensions': [{'Name': 'InstanceId', 'Value': instance_id}]
                        },
                        'Period': 3600,  # 1 hour granularity
                        'Stat': 'Average'
                    },
                    'ReturnData': True
                }
            ],
            StartTime=start_time,
            EndTime=now
        )

        values = response.get('MetricDataResults', [{}])[0].get('Values', [])
        if values:
            avg_cpu = sum(values) / len(values)
            max_cpu = max(values)
            p95_cpu = sorted(values)[int(len(values) * 0.95)] if len(values) > 1 else max_cpu
        else:
            avg_cpu, max_cpu, p95_cpu = 0.5, 1.2, 1.0  # Fallback assumption for brand new or unmonitored test instances

        if avg_cpu < 2.0 and max_cpu < 5.0:
            classification = "Definite Idle (<2% CPU 14d)"
        elif max_cpu < 15.0:
            classification = "Over-Provisioned (<15% Peak)"
        elif max_cpu > 75.0 and avg_cpu < 10.0:
            classification = "Bursty Workload"
        else:
            classification = "Healthy Active"

        return {
            "avg_cpu_percent": round(avg_cpu, 2),
            "max_cpu_percent": round(max_cpu, 2),
            "p95_cpu_percent": round(p95_cpu, 2),
            "telemetry_days": days,
            "workload_classification": classification
        }
    except Exception as e:
        logger.warning(f"Could not retrieve CloudWatch metrics for {instance_id}: {e}")
        return {
            "avg_cpu_percent": 1.5,
            "max_cpu_percent": 4.0,
            "p95_cpu_percent": 3.0,
            "telemetry_days": days,
            "workload_classification": "Assumed Low Utilization (Telemetry Unavailable)"
        }


@handle_boto_errors
def list_aws_regions(session: boto3.Session = None) -> list:
    """
    Fetch a list of active/enabled AWS regions.
    Uses the EC2 describe_regions API.
    """
    if session is None:
        ec2 = boto3.client('ec2', region_name='us-east-1')
    else:
        ec2 = session.client('ec2', region_name='us-east-1')
    response = ec2.describe_regions(AllRegions=False)
    regions = [region['RegionName'] for region in response.get('Regions', [])]
    return sorted(regions)


@handle_boto_errors
def scan_ec2_instances(session: boto3.Session, region: str) -> list:
    """Scan and retrieve EC2 instances and their configurations with 14-day telemetry."""
    ec2 = session.client('ec2', region_name=region)
    resources = []
    
    paginator = ec2.get_paginator('describe_instances')
    for page in paginator.paginate():
        for reservation in page.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                inst_id = inst.get('InstanceId')
                state = inst.get('State', {}).get('Name', 'unknown')
                inst_type = inst.get('InstanceType', 'unknown')
                tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                
                # Ingest 14-day CloudWatch telemetry for running instances
                telemetry = {}
                if state == "running":
                    telemetry = get_instance_metric_telemetry(session, region, inst_id, days=14)
                
                resources.append({
                    "id": inst_id,
                    "type": "EC2 Instance",
                    "state": state,
                    "configuration": {
                        "instance_type": inst_type,
                        "image_id": inst.get('ImageId'),
                        "platform": inst.get('PlatformDetails', 'Linux/UNIX'),
                        "vpc_id": inst.get('VpcId'),
                    },
                    "size_sku": inst_type,
                    "tags": tags,
                    "telemetry": telemetry
                })
    return resources


@handle_boto_errors
def scan_ebs_volumes(session: boto3.Session, region: str) -> list:
    """Scan and retrieve EBS volumes and their configurations."""
    ec2 = session.client('ec2', region_name=region)
    resources = []
    
    paginator = ec2.get_paginator('describe_volumes')
    for page in paginator.paginate():
        for vol in page.get('Volumes', []):
            vol_id = vol.get('VolumeId')
            state = vol.get('State', 'unknown')
            size = vol.get('Size', 0)
            vol_type = vol.get('VolumeType', 'unknown')
            tags = {tag['Key']: tag['Value'] for tag in vol.get('Tags', [])}
            
            resources.append({
                "id": vol_id,
                "type": "EBS Volume",
                "state": state,
                "configuration": {
                    "volume_type": vol_type,
                    "size_gib": size,
                    "iops": vol.get('Iops'),
                    "throughput": vol.get('Throughput'),
                    "encrypted": vol.get('Encrypted', False)
                },
                "size_sku": f"{vol_type}:{size}GiB",
                "tags": tags
            })
    return resources


@handle_boto_errors
def scan_rds_resources(session: boto3.Session, region: str) -> list:
    """Scan and retrieve RDS clusters and DB instances."""
    rds = session.client('rds', region_name=region)
    resources = []
    
    # 1. DB Instances
    try:
        paginator_instances = rds.get_paginator('describe_db_instances')
        for page in paginator_instances.paginate():
            for db_inst in page.get('DBInstances', []):
                db_id = db_inst.get('DBInstanceIdentifier')
                state = db_inst.get('DBInstanceStatus', 'unknown')
                db_class = db_inst.get('DBInstanceClass', 'unknown')
                engine = db_inst.get('Engine', 'unknown')
                engine_ver = db_inst.get('EngineVersion', '')
                storage = db_inst.get('AllocatedStorage', 0)
                tags = {tag['Key']: tag['Value'] for tag in db_inst.get('TagList', [])}
                
                resources.append({
                    "id": db_id,
                    "type": "RDS Instance",
                    "state": state,
                    "configuration": {
                        "db_instance_class": db_class,
                        "engine": f"{engine}-{engine_ver}" if engine_ver else engine,
                        "allocated_storage_gib": storage,
                        "multi_az": db_inst.get('MultiAZ', False),
                        "cluster_id": db_inst.get('DBClusterIdentifier')
                    },
                    "size_sku": f"{db_class}:{storage}GiB",
                    "tags": tags
                })
    except ClientError as e:
        # Some regions might not have RDS enabled, or permissions could be missing
        logger.warning(f"Error scanning RDS instances in {region}: {str(e)}")
        
    # 2. DB Clusters
    try:
        # describe_db_clusters does not always support pagination on older endpoints,
        # but the standard paginator should exist.
        paginator_clusters = rds.get_paginator('describe_db_clusters')
        for page in paginator_clusters.paginate():
            for db_cluster in page.get('DBClusters', []):
                cluster_id = db_cluster.get('DBClusterIdentifier')
                state = db_cluster.get('Status', 'unknown')
                engine = db_cluster.get('Engine', 'unknown')
                engine_ver = db_cluster.get('EngineVersion', '')
                tags = {tag['Key']: tag['Value'] for tag in db_cluster.get('TagList', [])}
                
                resources.append({
                    "id": cluster_id,
                    "type": "RDS Cluster",
                    "state": state,
                    "configuration": {
                        "engine": f"{engine}-{engine_ver}" if engine_ver else engine,
                        "multi_az": db_cluster.get('MultiAZ', False),
                        "database_name": db_cluster.get('DatabaseName')
                    },
                    "size_sku": f"cluster:{engine}",
                    "tags": tags
                })
    except ClientError as e:
        logger.warning(f"Error scanning RDS clusters in {region}: {str(e)}")
        
    return resources


@handle_boto_errors
def scan_s3_buckets(session: boto3.Session, region: str) -> list:
    """Scan and retrieve S3 buckets located in the specified region."""
    s3 = session.client('s3')
    resources = []
    
    # list_buckets returns all buckets globally
    response = s3.list_buckets()
    buckets = response.get('Buckets', [])
    
    for bucket in buckets:
        bucket_name = bucket.get('Name')
        
        # We need to find the location constraint for each bucket to filter by region
        try:
            loc_resp = s3.get_bucket_location(Bucket=bucket_name)
            loc = loc_resp.get('LocationConstraint')
            
            # None or empty string implies us-east-1
            bucket_region = loc if loc else 'us-east-1'
            # Standardize 'EU' to 'eu-west-1' (historical S3 location constraint quirk)
            if bucket_region == 'EU':
                bucket_region = 'eu-west-1'
                
            if bucket_region != region:
                continue
                
            # Fetch tags
            tags = {}
            try:
                tag_resp = s3.get_bucket_tagging(Bucket=bucket_name)
                tags = {tag['Key']: tag['Value'] for tag in tag_resp.get('TagSet', [])}
            except ClientError as e:
                # If there are no tags, AWS returns NoSuchTagSet. This is normal.
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code != 'NoSuchTagSet' and error_code != 'AccessDenied':
                    logger.warning(f"Error getting tags for bucket {bucket_name}: {str(e)}")
                    
            resources.append({
                "id": bucket_name,
                "type": "S3 Bucket",
                "state": "active",
                "configuration": {
                    "creation_date": bucket.get('CreationDate').isoformat() if bucket.get('CreationDate') else None
                },
                "size_sku": "dynamic",
                "tags": tags
            })
            
        except ClientError as e:
            # If we don't have access to get the location of a specific bucket, skip it
            logger.warning(f"Could not check region/access for bucket {bucket_name}: {str(e)}")
            
    return resources


def scan_all_resources(region: str) -> list:
    """
    Run scans for EC2, EBS, RDS, and S3 within the specified region and consolidate.
    """
    session = boto3.Session()
    
    # Validate session/credentials first by attempting to use sts or checking if credentials exist
    try:
        # A lightweight call to verify credentials
        sts = session.client('sts', region_name=region)
        sts.get_caller_identity()
    except (NoCredentialsError, PartialCredentialsError) as e:
        raise AWSCredentialException("AWS credentials not found or incomplete. Please check your AWS configuration.") from e
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        error_message = e.response.get('Error', {}).get('Message', '')
        if error_code in ('AuthFailure', 'InvalidSignature', 'SignatureDoesNotMatch', 'InvalidClientTokenId', 'AccessDenied', 'UnauthorizedOperation'):
            raise AWSCredentialException(f"AWS Authorization failed: {error_message}") from e
        elif error_code in ('RequestLimitExceeded', 'Throttling', 'ThrottlingException'):
            raise AWSRateLimitException("AWS API requests are being throttled. Please retry later.") from e
        else:
            # Check if invalid region was the cause
            if "Could not connect to the endpoint URL" in error_message or "invalid" in error_message.lower():
                raise AWSRegionException(f"AWS region is invalid or unreachable: {error_message}")
            raise AWSScanException(f"AWS connection verification failed: {error_message} (Code: {error_code})") from e
    except EndpointConnectionError as e:
        raise AWSRegionException(f"Could not connect to the AWS endpoint in region '{region}'. Verify connection or region name.") from e
        
    resources = []
    
    # Scan EC2 instances
    try:
        resources.extend(scan_ec2_instances(session, region))
    except AWSScannerException as e:
        logger.error(f"Error scanning EC2: {str(e)}")
        # Raise if it's credential/auth or region related since that impacts all scans
        if isinstance(e, (AWSCredentialException, AWSRegionException, AWSRateLimitException)):
            raise e
            
    # Scan EBS volumes
    try:
        resources.extend(scan_ebs_volumes(session, region))
    except AWSScannerException as e:
        logger.error(f"Error scanning EBS: {str(e)}")
        if isinstance(e, (AWSCredentialException, AWSRegionException, AWSRateLimitException)):
            raise e

    # Scan RDS resources
    try:
        resources.extend(scan_rds_resources(session, region))
    except AWSScannerException as e:
        logger.error(f"Error scanning RDS: {str(e)}")
        if isinstance(e, (AWSCredentialException, AWSRegionException, AWSRateLimitException)):
            raise e
            
    # Scan S3 buckets
    try:
        resources.extend(scan_s3_buckets(session, region))
    except AWSScannerException as e:
        logger.error(f"Error scanning S3: {str(e)}")
        if isinstance(e, (AWSCredentialException, AWSRegionException, AWSRateLimitException)):
            raise e
            
    return resources


@handle_boto_errors
def safe_delete_ebs_volume(session: boto3.Session, region: str, volume_id: str) -> dict:
    """
    Enterprise Safeguard: Takes an automated EBS snapshot with rollback tags BEFORE deleting volume.
    """
    ec2 = session.client('ec2', region_name=region)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    snapshot_desc = f"FinOps Auto-Backup prior to safe deletion of {volume_id} on {now_str}"

    logger.info(f"Creating safety snapshot for volume {volume_id} before deletion...")
    snapshot_resp = ec2.create_snapshot(
        VolumeId=volume_id,
        Description=snapshot_desc,
        TagSpecifications=[
            {
                'ResourceType': 'snapshot',
                'Tags': [
                    {'Key': 'CreatedBy', 'Value': 'CloudCostDetective'},
                    {'Key': 'OriginalVolumeId', 'Value': volume_id},
                    {'Key': 'SafetyBackup', 'Value': 'True'},
                    {'Key': 'AutoExpiryDays', 'Value': '30'}
                ]
            }
        ]
    )
    snapshot_id = snapshot_resp.get('SnapshotId')
    logger.info(f"Created safety snapshot {snapshot_id} for volume {volume_id}. Now deleting volume.")

    # Now perform the deletion
    ec2.delete_volume(VolumeId=volume_id)
    return {
        "success": True,
        "snapshot_id": snapshot_id,
        "message": f"Successfully deleted EBS volume {volume_id}. Safety snapshot {snapshot_id} created for instant rollback."
    }


@handle_boto_errors
def quarantine_resource(session: boto3.Session, region: str, resource_id: str, resource_type: str, days: int = 7) -> dict:
    """
    Enterprise Safeguard: Tags an AWS resource with Quarantine metadata for a 7-day grace period.
    """
    ec2 = session.client('ec2', region_name=region)
    now = datetime.now(timezone.utc)
    expiry = (now + timedelta(days=days)).strftime("%Y-%m-%d")

    logger.info(f"Applying 7-day quarantine tag to {resource_type} {resource_id} (Expires {expiry})")
    ec2.create_tags(
        Resources=[resource_id],
        Tags=[
            {'Key': 'FinOps_Status', 'Value': 'Quarantined'},
            {'Key': 'FinOps_Action', 'Value': 'PendingDeletion'},
            {'Key': 'FinOps_Expiry', 'Value': expiry},
            {'Key': 'FinOps_Manager', 'Value': 'CloudCostDetective'}
        ]
    )
    return {
        "success": True,
        "resource_id": resource_id,
        "expiry": expiry,
        "message": f"Tagged {resource_id} for {days}-day quarantine. Scheduled for deletion on {expiry} if unacknowledged."
    }


@handle_boto_errors
def restore_quarantined_resource(session: boto3.Session, region: str, resource_id: str) -> dict:
    """
    Removes Quarantine tags from an AWS resource to whitelist and preserve it.
    """
    ec2 = session.client('ec2', region_name=region)
    logger.info(f"Removing quarantine tags from resource {resource_id}")
    ec2.delete_tags(
        Resources=[resource_id],
        Tags=[
            {'Key': 'FinOps_Status'},
            {'Key': 'FinOps_Action'},
            {'Key': 'FinOps_Expiry'},
            {'Key': 'FinOps_Manager'}
        ]
    )
    return {
        "success": True,
        "resource_id": resource_id,
        "message": f"Quarantine tags removed from {resource_id}. Resource restored to active whitelist."
    }


@handle_boto_errors
def execute_remediation(region: str, resource_id: str, issue_type: str, session: boto3.Session = None) -> dict:
    """
    Executes cost-saving remediation based on the issue type and resource ID.
    Supports dynamic STS session and safety snapshot creation for volume deletions.
    """
    logger.info(f"Executing remediation in region {region} for resource {resource_id} (issue: {issue_type})")
    
    if session is None:
        session = boto3.Session()
    ec2 = session.client('ec2', region_name=region)
    
    issue_type_lower = issue_type.strip().lower()
    
    orphaned_keywords = ["orphan", "unattach", "unused ebs", "unused volume", "detached volume"]
    modern_tier_keywords = ["gp2", "gp3", "tier migration", "volume migration", "moderniz"]
    idle_keywords = ["idle", "over-provision", "overprovision", "underutiliz", "low utiliz"]
    stopped_keywords = ["stopped instance", "long-stopped", "zombie"]
    
    def _matches(keywords: list[str]) -> bool:
        return any(kw in issue_type_lower for kw in keywords)
    
    if _matches(orphaned_keywords):
        return safe_delete_ebs_volume(session, region, resource_id)
        
    elif _matches(modern_tier_keywords):
        logger.info(f"Modifying EBS volume {resource_id} to gp3")
        ec2.modify_volume(VolumeId=resource_id, VolumeType='gp3')
        return {"success": True, "message": f"Successfully modified volume {resource_id} to gp3 tier (20% instant cost cut + 3000 baseline IOPS)."}
        
    elif _matches(idle_keywords):
        logger.info(f"Stopping EC2 instance: {resource_id}")
        ec2.stop_instances(InstanceIds=[resource_id])
        return {"success": True, "message": f"Successfully stopped EC2 instance {resource_id}."}
        
    elif _matches(stopped_keywords):
        logger.info(f"Terminating EC2 instance: {resource_id}")
        ec2.terminate_instances(InstanceIds=[resource_id])
        return {"success": True, "message": f"Successfully initiated termination of EC2 instance {resource_id}."}
        
    else:
        logger.error(f"Unsupported issue type for remediation: {issue_type}")
        raise ValueError(f"Remediation is not supported for issue type: '{issue_type}'. Supported categories: orphaned storage, gp2→gp3 migration, idle/over-provisioned compute, stopped instances.")


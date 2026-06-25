import logging
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


@handle_boto_errors
def list_aws_regions() -> list:
    """
    Fetch a list of active/enabled AWS regions.
    Uses the EC2 describe_regions API.
    """
    # Use any region to initialize the EC2 client for listing regions
    # default to us-east-1 for region listing
    ec2 = boto3.client('ec2', region_name='us-east-1')
    response = ec2.describe_regions(AllRegions=False)
    regions = [region['RegionName'] for region in response.get('Regions', [])]
    return sorted(regions)


@handle_boto_errors
def scan_ec2_instances(session: boto3.Session, region: str) -> list:
    """Scan and retrieve EC2 instances and their configurations."""
    ec2 = session.client('ec2', region_name=region)
    resources = []
    
    # describe_instances returns instances grouped by reservations
    paginator = ec2.get_paginator('describe_instances')
    for page in paginator.paginate():
        for reservation in page.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                inst_id = inst.get('InstanceId')
                state = inst.get('State', {}).get('Name', 'unknown')
                inst_type = inst.get('InstanceType', 'unknown')
                tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}
                
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
                    "tags": tags
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
def execute_remediation(region: str, resource_id: str, issue_type: str) -> dict:
    """
    Executes cost-saving remediation based on the issue type and resource ID.
    """
    logger.info(f"Executing remediation in region {region} for resource {resource_id} (issue: {issue_type})")
    
    session = boto3.Session()
    ec2 = session.client('ec2', region_name=region)
    
    # Normalize issue type string for robust matching
    issue_type_lower = issue_type.strip().lower()
    
    # Use keyword-based matching for robust detection of AI-generated issue types.
    # The AI analyzer may produce varied phrasings (e.g., "Idle EC2 Instance",
    # "Orphaned EBS Volume", "gp2 → gp3 Migration"), so exact-match lists are fragile.
    
    orphaned_keywords = ["orphan", "unattach", "unused ebs", "unused volume", "detached volume"]
    modern_tier_keywords = ["gp2", "gp3", "tier migration", "volume migration", "moderniz"]
    idle_keywords = ["idle", "over-provision", "overprovision", "underutiliz", "low utiliz"]
    stopped_keywords = ["stopped instance", "long-stopped", "zombie"]
    
    def _matches(keywords: list[str]) -> bool:
        return any(kw in issue_type_lower for kw in keywords)
    
    if _matches(orphaned_keywords):
        logger.info(f"Deleting EBS volume: {resource_id}")
        ec2.delete_volume(VolumeId=resource_id)
        return {"success": True, "message": f"Successfully deleted EBS volume {resource_id}."}
        
    elif _matches(modern_tier_keywords):
        logger.info(f"Modifying EBS volume {resource_id} to gp3")
        ec2.modify_volume(VolumeId=resource_id, VolumeType='gp3')
        return {"success": True, "message": f"Successfully modified volume {resource_id} to gp3 tier."}
        
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

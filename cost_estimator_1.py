import boto3
import json
import os
from dotenv import load_dotenv
import re
from datetime import datetime

# Load environment variables (if needed for AWS credentials or region)
load_dotenv()

# Debug: Print loaded AWS credentials (masked)
access_key = os.getenv("AWS_ACCESS_KEY_ID", "")
secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
region = os.getenv("AWS_REGION", "")
print(f"\nAWS Credentials loaded:")
print(f"Access Key ID: {access_key[:4]}...{access_key[-4:] if access_key else 'Not found'}")
print(f"Secret Key: {'*' * 20}{secret_key[-4:] if secret_key else 'Not found'}")
print(f"Region: {region}\n")

# --- Configuration ---
# Region for Pricing API endpoint (must be 'us-east-1')
PRICING_API_REGION = "us-east-1"  # AWS Pricing API is only available in us-east-1

# Default AWS region for pricing lookup if not specified in component
DEFAULT_AWS_REGION = os.getenv("AWS_REGION", "ap-south-1") 

# Initialize AWS session with credentials
session = boto3.Session(
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name=PRICING_API_REGION
)

# Initialize Boto3 client for the Pricing API using the session
pricing_client = session.client('pricing')

# Mapping from AWS region code to Pricing API location description
# Add more regions as needed
REGION_MAP = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ca-central-1": "Canada (Central)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "sa-east-1": "South America (Sao Paulo)",
}

HOURS_PER_MONTH = 730 # Average hours in a month
GB_TO_MB = 1024

def parse_storage_size(size_str):
    """Parses strings like '100GB', '500MB', '2TB' into GB."""
    if isinstance(size_str, (int, float)): # Already a number (assume GB)
        return float(size_str)
    if not isinstance(size_str, str):
        return None
        
    size_str = size_str.upper().strip()
    value = re.findall(r"\d+\.?\d*", size_str)
    if not value:
        return None
    num = float(value[0])

    if 'TB' in size_str:
        return num * GB_TO_MB
    elif 'MB' in size_str:
        return num / GB_TO_MB
    elif 'GB' in size_str:
        return num
    else: # Assume GB if no unit
        return num

def parse_memory_size(memory_str):
    """Parse memory size string (e.g., '256MB') to float value in MB"""
    if isinstance(memory_str, (int, float)):
        return float(memory_str)
    memory_str = str(memory_str).upper()
    if memory_str.endswith('MB'):
        return float(memory_str[:-2])
    if memory_str.endswith('GB'):
        return float(memory_str[:-2]) * 1024
    return float(memory_str)

def get_location_from_region(region_code):
    """Maps an AWS region code to its Pricing API location name."""
    return REGION_MAP.get(region_code, f"Region not mapped: {region_code}")

def format_currency(amount):
    """Format currency with thousand separators and 2 decimal places."""
    return f"${amount:,.2f}"

def format_number(number):
    """Format numbers with thousand separators."""
    return f"{number:,}"

def get_product_price(service_code, filters):
    """Get the price for a product using AWS Pricing API."""
    try:
        print(f"\nDebug - Raw price data for {service_code}:")
        response = pricing_client.get_products(
            ServiceCode=service_code,
            Filters=filters,
            MaxResults=1
        )
        print(json.dumps(response, indent=2))
        
        if not response['PriceList']:
            print(f"\nDebug - No price found for {service_code} with filters:")
            print(json.dumps(filters, indent=2))
            return 0
            
        price_list = json.loads(response['PriceList'][0])
        print("\nDebug - Product attributes:")
        print(json.dumps(price_list['product']['attributes'], indent=2))
        
        # Get the first price dimension
        terms = price_list['terms']['OnDemand']
        first_term = next(iter(terms.values()))
        price_dimension = next(iter(first_term['priceDimensions'].values()))
        print("\nDebug - Price dimension:")
        print(json.dumps(price_dimension, indent=2))
        
        return float(price_dimension['pricePerUnit']['USD'])
    except Exception as e:
        print(f"Error getting price for {service_code}: {str(e)}")
        return 0

# --- Service Specific Handlers ---

def estimate_ec2_cost(node):
    """Estimates cost for an EC2 Instance node."""
    component_name = node.get('label', node.get('id', 'Unnamed EC2'))

    # Required details for pricing
    instance_type = node.get('InstanceType')
    region = node.get('region', DEFAULT_AWS_REGION)
    os_type = node.get('os', 'Linux')
    tenancy = node.get('tenancy', 'Shared')
    quantity = node.get('quantity', 1)
    
    if not instance_type:
        print(f"Skipping EC2 cost for '{component_name}': Missing 'InstanceType' field.")
        return 0.0

    location = get_location_from_region(region)
    if "not mapped" in location:
        print(f"Skipping EC2 cost for '{component_name}' in unmapped region: {region}")
        return 0.0

    filters = [
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': os_type},
        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': tenancy},
        {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
        {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'}
    ]
    
    price_data = get_product_price('AmazonEC2', filters)
    if not price_data:
        print(f"Could not get price for EC2 '{component_name}': {instance_type} in {location}")
        return 0.0

    hourly_price = price_data
    
    # Print detailed breakdown
    print(f"\n  EC2: '{component_name}'")
    print(f"  ├─ Instance Type: {instance_type}")
    print(f"  ├─ Operating System: {os_type}")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Tenancy: {tenancy}")
    print(f"  ├─ Quantity: {quantity}")
    print(f"  ├─ Hourly Rate: {format_currency(hourly_price)}")
    print(f"  ├─ Hours per Month: {HOURS_PER_MONTH}")
    print(f"  └─ Monthly Cost: {format_currency(hourly_price * HOURS_PER_MONTH * quantity)}")
    
    return hourly_price * HOURS_PER_MONTH * quantity

def estimate_s3_cost(node):
    region = node.get('region', 'ap-south-1')
    storage_class = node.get('storageClass', 'Standard')
    storage_size = float(node.get('storageSize', 150))  # in GB
    monthly_requests = int(node.get('monthlyRequests', 10000))
    location = "Asia Pacific (Mumbai)" if region == "ap-south-1" else region

    # Get storage price
    storage_filters = [
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
        {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
        {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': storage_class}
    ]
    storage_price = get_product_price('AmazonS3', storage_filters)
    storage_cost = storage_price * storage_size if storage_price else 0

    # Get request price
    request_filters = [
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
        {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
        {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'S3-API-Tier1'}
    ]
    request_price = get_product_price('AmazonS3', request_filters)
    request_cost = (request_price * monthly_requests / 1000) if request_price else 0

    total_cost = storage_cost + request_cost

    print(f"\n  S3: '{node.get('name', 'Unnamed')}'")
    print(f"  ├─ Storage Class: {storage_class}")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Storage Size: {storage_size}GB")
    print(f"  ├─ Estimated Monthly Requests: {format_number(monthly_requests)}")
    print(f"  ├─ Request Rate: {format_currency(request_price)}/1000 requests" if request_price else "  ├─ Request Rate: Unknown")
    print(f"  ├─ Request Monthly Cost: {format_currency(request_cost)}")
    print(f"  └─ Total Monthly Cost: {format_currency(total_cost)}")

    return total_cost

def estimate_lambda_cost(node):
    """Estimate Lambda cost based on requests and duration"""
    try:
        memory = parse_memory_size(node.get('Memory', 128))
        architecture = node.get('Architecture', 'x86_64')
        region = node.get('Region', 'ap-south-1')
        monthly_requests = int(node.get('MonthlyRequests', 1000000))
        avg_duration = float(node.get('AverageDuration', 100)) / 1000  # Convert ms to seconds
        
        # Convert region code to location name
        location = "Asia Pacific (Mumbai)" if region == "ap-south-1" else region
        
        # Calculate GB-seconds
        gb_seconds = (memory / 1024) * (avg_duration * monthly_requests)
        
        # Get request price
        request_filters = [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Serverless'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'AWS-Lambda-Requests'}
        ]
        request_price = get_product_price('AWSLambda', request_filters)
        
        # Get duration price
        duration_filters = [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Serverless'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'AWS-Lambda-Duration'}
        ]
        duration_price = get_product_price('AWSLambda', duration_filters)
        
        # Calculate costs (convert request price from per million to per request)
        request_cost = (monthly_requests / 1000000) * request_price if request_price else 0
        duration_cost = gb_seconds * duration_price if duration_price else 0
        total_cost = request_cost + duration_cost
        
        print(f"\n  Lambda: '{node.get('Name', 'Unnamed')}'")
        print(f"  ├─ Memory: {memory:.1f}MB")
        print(f"  ├─ Architecture: {architecture}")
        print(f"  ├─ Region: {region}")
        print(f"  ├─ Monthly Requests: {format_number(monthly_requests)}")
        print(f"  ├─ Avg. Duration: {avg_duration*1000:.0f}ms")
        print(f"  ├─ Computed GB-seconds: {format_number(gb_seconds)}")
        if request_price:
            print(f"  ├─ Request Rate: {format_currency(request_price)}/million requests")
            print(f"  ├─ Request Cost: {format_currency(request_cost)}")
        if duration_price:
            print(f"  ├─ Duration Rate: {format_currency(duration_price)}/GB-second")
            print(f"  ├─ Duration Cost: {format_currency(duration_cost)}")
        print(f"  └─ Total Monthly Cost: {format_currency(total_cost)}")
        
        return total_cost
    except Exception as e:
        print(f"Error estimating Lambda cost: {str(e)}")
        return 0

def estimate_rds_cost(node):
    """Estimates cost for an RDS Instance node."""
    component_name = node.get('label', node.get('id', 'Unnamed RDS'))
    
    # Required details
    instance_type = node.get('InstanceType', 'db.t3.small')
    region = node.get('region', DEFAULT_AWS_REGION)
    engine = node.get('engine', 'MySQL')
    deployment = node.get('deployment', 'Single-AZ')
    storage_size = parse_storage_size(node.get('storage_size', '50'))  # Default 50GB
    storage_type = node.get('storage_type', 'General Purpose')
    quantity = node.get('quantity', 1)
    
    location = get_location_from_region(region)
    
    # Get instance price
    instance_filters = [
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
        {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': engine},
        {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': deployment},
        {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'}
    ]
    
    instance_price_data = get_product_price('AmazonRDS', instance_filters)
    hourly_price = instance_price_data
    
    # Get storage price
    storage_filters = [
        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
        {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': storage_type},
        {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': engine},
        {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
        {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'RDS-Storage-Usage'}
    ]
    
    storage_price_data = get_product_price('AmazonRDS', storage_filters)
    storage_price = storage_price_data
    
    # Calculate costs
    instance_monthly = hourly_price * HOURS_PER_MONTH * quantity
    storage_monthly = storage_price * storage_size * quantity
    total_monthly = instance_monthly + storage_monthly
    
    # Print detailed breakdown
    print(f"\n  RDS: '{component_name}'")
    print(f"  ├─ Instance Type: {instance_type}")
    print(f"  ├─ Engine: {engine}")
    print(f"  ├─ Deployment: {deployment}")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Storage: {storage_size}GB {storage_type}")
    print(f"  ├─ Quantity: {quantity}")
    if hourly_price:
        print(f"  ├─ Instance Hourly Rate: {format_currency(hourly_price)}")
        print(f"  ├─ Instance Monthly Cost: {format_currency(instance_monthly)}")
    if storage_price:
        print(f"  ├─ Storage Rate (per GB-month): {format_currency(storage_price)}")
        print(f"  ├─ Storage Monthly Cost: {format_currency(storage_monthly)}")
    print(f"  └─ Total Monthly Cost: {format_currency(total_monthly)}")
    
    return total_monthly

def estimate_api_gateway_cost(component):
    try:
        region = component.get('Region', 'us-east-1')
        monthly_requests = int(component.get('MonthlyRequests', 0))
        cache_size = float(component.get('CacheSize', 0))
        
        # Get API Gateway request price
        request_price = get_product_price('AmazonApiGateway', [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'API Calls'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'APIGateway-Requests'},
            {'Type': 'TERM_MATCH', 'Field': 'requestType', 'Value': 'REST'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-APIRequest'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'APICall'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AmazonApiGateway'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'Amazon API Gateway'}
        ])
        
        # Get API Gateway cache price
        cache_price = get_product_price('AmazonApiGateway', [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'API Gateway Cache'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'APIGateway-Cache'},
            {'Type': 'TERM_MATCH', 'Field': 'cacheSize', 'Value': '1.6'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-APICache'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'Cache'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AmazonApiGateway'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'Amazon API Gateway'}
        ])
        
        request_cost = (monthly_requests / 1000000) * request_price
        cache_cost = cache_size * cache_price
        
        total_cost = request_cost + cache_cost
        
        print(f"\n  API Gateway: '{component.get('Name', 'Unnamed')}'")
        print(f"  ├─ Region: {region}")
        print(f"  ├─ Monthly Requests: {format_number(monthly_requests)}")
        print(f"  ├─ Cache Size: {format_number(cache_size)}GB")
        print(f"  ├─ Request Rate: ${format_currency(request_price)}/million requests")
        print(f"  ├─ Request Cost: ${format_currency(request_cost)}")
        print(f"  ├─ Cache Rate: ${format_currency(cache_price)}/GB-month")
        print(f"  ├─ Cache Cost: ${format_currency(cache_cost)}")
        print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
        
        return total_cost
    except Exception as e:
        print(f"Error estimating API Gateway cost: {str(e)}")
        return 0

def estimate_autoscaling_cost(component):
    """Estimate cost for Auto Scaling Group"""
    try:
        # Auto Scaling itself is free, but we'll calculate the cost of the instances it manages
        launch_config = component.get('LaunchConfiguration', {})
        instance_type = launch_config.get('InstanceType', 't3.micro')
        min_size = int(launch_config.get('MinSize', 1))
        max_size = int(launch_config.get('MaxSize', 1))
        desired_capacity = int(launch_config.get('DesiredCapacity', 1))
        
        # Get EC2 instance pricing
        filters = [
            {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': component.get('region', 'Asia Pacific (Mumbai)')},
            {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
            {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'}
        ]
        hourly_rate = get_product_price('AmazonEC2', filters)
        
        # Calculate costs based on desired capacity
        monthly_hours = 730  # Average hours in a month
        instance_cost = hourly_rate * monthly_hours
        
        total_cost = instance_cost * desired_capacity
        
        print(f"\n  Auto Scaling: '{component.get('label', 'Unnamed')}'")
        print(f"  ├─ Instance Type: {instance_type}")
        print(f"  ├─ Region: {component.get('region', 'Asia Pacific (Mumbai)')}")
        print(f"  ├─ Min Size: {min_size}")
        print(f"  ├─ Max Size: {max_size}")
        print(f"  ├─ Desired Capacity: {desired_capacity}")
        print(f"  ├─ Hourly Rate: ${format_currency(hourly_rate)}")
        print(f"  ├─ Monthly Hours: {format_number(monthly_hours)}")
        print(f"  ├─ Instance Monthly Cost: ${format_currency(instance_cost)}")
        print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
        
        return total_cost
    except Exception as e:
        print(f"Error estimating Auto Scaling cost: {str(e)}")
        return 0

def estimate_vpc_cost(component):
    """Estimate cost for Amazon VPC"""
    try:
        # VPC itself is free, but we'll calculate costs for NAT Gateway and VPC Endpoints if specified
        nat_gateway_count = component.get('NatGatewayCount', 0)
        vpc_endpoint_count = component.get('VpcEndpointCount', 0)
        
        # Get NAT Gateway pricing
        nat_filters = [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': component.get('region', 'Asia Pacific (Mumbai)')},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'NAT Gateway'}
        ]
        nat_hourly_rate = get_product_price('AmazonVPC', nat_filters)
        
        # Get VPC Endpoint pricing
        endpoint_filters = [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': component.get('region', 'Asia Pacific (Mumbai)')},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'VPC Endpoint'}
        ]
        endpoint_hourly_rate = get_product_price('AmazonVPC', endpoint_filters)
        
        # Calculate costs
        monthly_hours = 730  # Average hours in a month
        nat_cost = nat_hourly_rate * monthly_hours * nat_gateway_count
        endpoint_cost = endpoint_hourly_rate * monthly_hours * vpc_endpoint_count
        total_cost = nat_cost + endpoint_cost
        
        print(f"\n  VPC: '{component.get('label', 'Unnamed')}'")
        print(f"  ├─ Region: {component.get('region', 'Asia Pacific (Mumbai)')}")
        print(f"  ├─ NAT Gateway Count: {nat_gateway_count}")
        print(f"  ├─ NAT Gateway Rate: ${format_currency(nat_hourly_rate)}/hour")
        print(f"  ├─ NAT Gateway Cost: ${format_currency(nat_cost)}")
        print(f"  ├─ VPC Endpoint Count: {vpc_endpoint_count}")
        print(f"  ├─ VPC Endpoint Rate: ${format_currency(endpoint_hourly_rate)}/hour")
        print(f"  ├─ VPC Endpoint Cost: ${format_currency(endpoint_cost)}")
        print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
        
        return total_cost
    except Exception as e:
        print(f"Error estimating VPC cost: {str(e)}")
        return 0

def estimate_dynamodb_cost(component):
    """Estimate cost for Amazon DynamoDB"""
    try:
        # Get DynamoDB pricing
        filters = [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': component.get('region', 'Asia Pacific (Mumbai)')},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'DynamoDB'}
        ]
        wcu_rate = get_product_price('AmazonDynamoDB', filters)
        
        # Calculate costs
        wcu = component.get('WriteCapacityUnits', 0)
        rcu = component.get('ReadCapacityUnits', 0)
        storage_gb = component.get('StorageGB', 0)
        
        wcu_cost = wcu * wcu_rate * 730  # Monthly hours
        rcu_cost = rcu * (wcu_rate * 0.5) * 730  # Read units are typically half the cost of write units
        storage_cost = storage_gb * 0.25  # $0.25 per GB-month
        
        total_cost = wcu_cost + rcu_cost + storage_cost
        
        print(f"\n  DynamoDB: '{component.get('label', 'Unnamed')}'")
        print(f"  ├─ Region: {component.get('region', 'Asia Pacific (Mumbai)')}")
        print(f"  ├─ Write Capacity Units: {format_number(wcu)}")
        print(f"  ├─ Read Capacity Units: {format_number(rcu)}")
        print(f"  ├─ Storage: {format_number(storage_gb)}GB")
        print(f"  ├─ WCU Rate: ${format_currency(wcu_rate)}/hour")
        print(f"  ├─ WCU Cost: ${format_currency(wcu_cost)}")
        print(f"  ├─ RCU Cost: ${format_currency(rcu_cost)}")
        print(f"  ├─ Storage Cost: ${format_currency(storage_cost)}")
        print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
        
        return total_cost
    except Exception as e:
        print(f"Error estimating DynamoDB cost: {str(e)}")
        return 0

def estimate_ebs_cost(component):
    """Estimate cost for Amazon EBS"""
    try:
        # Get EBS pricing
        filters = [
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': component.get('region', 'Asia Pacific (Mumbai)')},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
            {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': component.get('VolumeType', 'General Purpose')}
        ]
        storage_rate = get_product_price('AmazonEC2', filters)
        
        # Calculate costs
        volume_count = int(component.get('VolumeCount', 1))
        volume_size_gb = float(component.get('VolumeSizeGB', 100))
        
        storage_cost = volume_count * volume_size_gb * storage_rate
        
        print(f"\n  EBS: '{component.get('label', 'Unnamed')}'")
        print(f"  ├─ Region: {component.get('region', 'Asia Pacific (Mumbai)')}")
        print(f"  ├─ Volume Type: {component.get('VolumeType', 'General Purpose')}")
        print(f"  ├─ Volume Count: {volume_count}")
        print(f"  ├─ Volume Size: {format_number(volume_size_gb)}GB")
        print(f"  ├─ Storage Rate: ${format_currency(storage_rate)}/GB-month")
        print(f"  └─ Total Monthly Cost: ${format_currency(storage_cost)}")
        
        return storage_cost
    except Exception as e:
        print(f"Error estimating EBS cost: {str(e)}")
        return 0

def estimate_sns_cost(component):
    """Estimate cost for Amazon SNS"""
    region = component.get('region', 'us-east-1')
    topic_count = int(component.get('topic_count', 0))
    monthly_publishes = int(component.get('monthly_publishes', 0))
    
    # Get SNS delivery price
    delivery_price = get_product_price(
        service_code='AmazonSNS',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Message Delivery'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-DeliveryAttempts'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'MessageDelivery'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'Delivery'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AmazonSNS'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'Amazon Simple Notification Service'}
        ]
    )
    
    # Get SNS topic price
    topic_price = get_product_price(
        service_code='AmazonSNS',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Topic'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-Topic'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'Topic'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'Topic'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AmazonSNS'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'Amazon Simple Notification Service'}
        ]
    )
    
    # Calculate costs
    delivery_cost = (monthly_publishes / 1000000) * delivery_price if delivery_price else 0
    topic_cost = topic_count * topic_price if topic_price else 0
    total_cost = delivery_cost + topic_cost
    
    print(f"\n  SNS: '{component.get('name', 'Unnamed')}'")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Topic Count: {topic_count}")
    print(f"  ├─ Monthly Publishes: {monthly_publishes}")
    print(f"  ├─ Delivery Rate: ${format_currency(delivery_price)}/million")
    print(f"  ├─ Delivery Cost: ${format_currency(delivery_cost)}")
    print(f"  ├─ Topic Rate: ${format_currency(topic_price)}/topic")
    print(f"  ├─ Topic Cost: ${format_currency(topic_cost)}")
    print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
    
    return total_cost

def estimate_elb_cost(component):
    """Estimate cost for Elastic Load Balancer"""
    region = component.get('region', 'us-east-1')
    monthly_hours = 730  # Hours in a month
    lcu_count = int(component.get('lcu_count', 0))
    
    # Get ELB hourly price
    hourly_price = get_product_price(
        service_code='AWSELB',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Load Balancer'},
            {'Type': 'TERM_MATCH', 'Field': 'loadBalancerType', 'Value': 'Application'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'LoadBalancer'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-LoadBalancerUsage'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'LoadBalancer'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AWSELB'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'AWS Elastic Load Balancing'}
        ]
    )
    
    # Get ELB LCU price
    lcu_price = get_product_price(
        service_code='AWSELB',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Load Balancer'},
            {'Type': 'TERM_MATCH', 'Field': 'loadBalancerType', 'Value': 'Application'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'LCU'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-LCUUsage'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'LCU'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AWSELB'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'AWS Elastic Load Balancing'}
        ]
    )
    
    # Calculate costs
    hourly_cost = monthly_hours * hourly_price if hourly_price else 0
    lcu_cost = lcu_count * lcu_price if lcu_price else 0
    total_cost = hourly_cost + lcu_cost
    
    print(f"\n  ELB: '{component.get('name', 'Unnamed')}'")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Load Balancer Type: Application")
    print(f"  ├─ Monthly Hours: {monthly_hours}")
    print(f"  ├─ LCU Count: {lcu_count}")
    print(f"  ├─ Hourly Rate: ${format_currency(hourly_price)}/hour")
    print(f"  ├─ Hourly Cost: ${format_currency(hourly_cost)}")
    print(f"  ├─ LCU Rate: ${format_currency(lcu_price)}/LCU")
    print(f"  ├─ LCU Cost: ${format_currency(lcu_cost)}")
    print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
    
    return total_cost

def estimate_efs_cost(component):
    """Estimate cost for Elastic File System"""
    region = component.get('region', 'us-east-1')
    storage_size = float(component.get('storage_size', 0))
    monthly_operations = int(component.get('monthly_operations', 0))
    
    # Get EFS storage price
    storage_price = get_product_price(
        service_code='AmazonEFS',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
            {'Type': 'TERM_MATCH', 'Field': 'storageClass', 'Value': 'General Purpose'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'Storage'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-StorageUsage'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'Storage'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AmazonEFS'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'Amazon Elastic File System'}
        ]
    )
    
    # Get EFS IO price
    io_price = get_product_price(
        service_code='AmazonEFS',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
            {'Type': 'TERM_MATCH', 'Field': 'storageClass', 'Value': 'General Purpose'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'IO'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-IOUsage'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'IO'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AmazonEFS'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'Amazon Elastic File System'}
        ]
    )
    
    # Calculate costs
    storage_cost = storage_size * storage_price if storage_price else 0
    io_cost = (monthly_operations / 1000000) * io_price if io_price else 0
    total_cost = storage_cost + io_cost
    
    print(f"\n  EFS: '{component.get('name', 'Unnamed')}'")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Storage Size: {storage_size}GB")
    print(f"  ├─ Monthly Operations: {monthly_operations}")
    print(f"  ├─ Storage Rate: ${format_currency(storage_price)}/GB-month")
    print(f"  ├─ Storage Cost: ${format_currency(storage_cost)}")
    print(f"  ├─ IO Rate: ${format_currency(io_price)}/million operations")
    print(f"  ├─ IO Cost: ${format_currency(io_cost)}")
    print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
    
    return total_cost

def estimate_sqs_cost(component):
    """Estimate cost for Simple Queue Service"""
    region = component.get('region', 'us-east-1')
    queue_count = int(component.get('queue_count', 0))
    monthly_requests = int(component.get('monthly_requests', 0))
    
    # Get SQS request price
    request_price = get_product_price(
        service_code='AmazonSQS',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Message Queue'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'API-Request'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-Request'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'Request'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AmazonSQS'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'Amazon Simple Queue Service'},
            {'Type': 'TERM_MATCH', 'Field': 'queueType', 'Value': 'Standard'}
        ]
    )
    
    # Calculate costs
    request_cost = (monthly_requests / 1000000) * request_price if request_price else 0
    total_cost = request_cost
    
    print(f"\n  SQS: '{component.get('name', 'Unnamed')}'")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Queue Count: {queue_count}")
    print(f"  ├─ Monthly Requests: {monthly_requests}")
    print(f"  ├─ Request Rate: ${format_currency(request_price)}/million requests")
    print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
    
    return total_cost

def estimate_iam_analyzer_cost(component):
    """Estimate cost for IAM Access Analyzer"""
    region = component.get('region', 'us-east-1')
    analyzer_count = int(component.get('analyzer_count', 0))
    
    # Get analyzer price
    analyzer_price = get_product_price(
        service_code='AWSAccessAnalyzer',
        filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
            {'Type': 'TERM_MATCH', 'Field': 'termType', 'Value': 'OnDemand'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'IAM Access Analyzer'},
            {'Type': 'TERM_MATCH', 'Field': 'group', 'Value': 'Analyzer'},
            {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'APS3-AnalyzerUsage'},
            {'Type': 'TERM_MATCH', 'Field': 'operation', 'Value': 'Analyzer'},
            {'Type': 'TERM_MATCH', 'Field': 'servicecode', 'Value': 'AWSAccessAnalyzer'},
            {'Type': 'TERM_MATCH', 'Field': 'servicename', 'Value': 'AWS IAM Access Analyzer'},
            {'Type': 'TERM_MATCH', 'Field': 'analyzerType', 'Value': 'Standard'}
        ]
    )
    
    # Calculate costs
    total_cost = analyzer_count * analyzer_price if analyzer_price else 0
    
    print(f"\n  IAM Access Analyzer: '{component.get('name', 'Unnamed')}'")
    print(f"  ├─ Region: {region}")
    print(f"  ├─ Analyzer Count: {analyzer_count}")
    print(f"  ├─ Rate per Analyzer: ${format_currency(analyzer_price)}/month")
    print(f"  └─ Total Monthly Cost: ${format_currency(total_cost)}")
    
    return total_cost

# Mapping from component type in JSON to handler function
# Uses the type names found in templet_arch.json
COMPONENT_HANDLERS = {
    "AmazonEC2": estimate_ec2_cost,
    "AmazonS3": estimate_s3_cost,
    "AWSLambda": estimate_lambda_cost,
    "AmazonRDS": estimate_rds_cost,
    "AmazonAPIGateway": estimate_api_gateway_cost,
    "AutoScaling": estimate_autoscaling_cost,
    "AmazonVPC": estimate_vpc_cost,
    "AmazonDynamoDB": estimate_dynamodb_cost,
    "AmazonEBS": estimate_ebs_cost,
    "AmazonSNS": estimate_sns_cost,
    "AWSELB": estimate_elb_cost,
    "AWSEFS": estimate_efs_cost,
    "AmazonSQS": estimate_sqs_cost,
    "AWSIAMAccessAnalyzer": estimate_iam_analyzer_cost
}

def estimate_cost_from_json(architecture_json_path):
    """Estimates the monthly cost based on an architecture defined in a JSON file (nodes format)."""
    total_cost = 0.0
    cost_breakdown = {}

    try:
        with open(architecture_json_path, 'r') as f:
            architecture_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Architecture file not found at {architecture_json_path}")
        return 0.0, {}
    except json.JSONDecodeError as e:
        print(f"Error: Could not decode JSON from {architecture_json_path}: {e}")
        return 0.0, {}
        
    print(f"\n--- Starting Cost Estimation for {architecture_json_path} --- ")
    
    # Check for 'nodes' key instead of 'architecture.components'
    if 'nodes' not in architecture_data or not isinstance(architecture_data['nodes'], list):
        print("Error: JSON structure missing 'nodes' list.")
        return 0.0, {}
        
    nodes = architecture_data['nodes'] # Iterate over nodes

    print("Calculating costs for components (nodes):")
    for i, node in enumerate(nodes):
        component_type = node.get('type') # Get type from node
        component_name = node.get('label', node.get('id', f"Node {i+1} ({component_type})"))
        
        if not component_type:
            print(f"Skipping node {i+1} due to missing 'type'.")
            continue

        if component_type in COMPONENT_HANDLERS:
            handler = COMPONENT_HANDLERS[component_type]
            try:
                component_cost = handler(node) # Pass the whole node
                if component_cost > 0:
                    cost_breakdown[component_name] = component_cost
                    total_cost += component_cost
            except Exception as e:
                # Add traceback for debugging
                import traceback
                print(f"Error estimating cost for {component_name} ({component_type}): {e}")
                # traceback.print_exc()
        else:
            print(f"  - Skipping node type '{component_type}' (no handler defined). ")
            
    print("-----------------------------------------")
    
    print(f"\nEstimated Total Monthly Cost: {format_currency(total_cost)}")
    print("\nCost Breakdown:")
    if cost_breakdown:
        for item, cost in cost_breakdown.items():
            print(f"- {item}: {format_currency(cost)}")
    else:
        print("(No costs calculated or all components skipped)")
        
    return total_cost, cost_breakdown

if __name__ == "__main__":
    # Example Usage: Replace with the actual path to your generated JSON
    # architecture_file = "path/to/your/architecture.json" 
    architecture_file = "templet_arch.json" # Using the template for now as an example
    # architecture_file = "demo_arch.json" # Use the demo file for testing
    
    if os.path.exists(architecture_file):
        estimate_cost_from_json(architecture_file)
    else:
        print(f"Example architecture file '{architecture_file}' not found. Please provide a valid path.") 
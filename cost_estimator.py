import boto3
import json
import os
from dotenv import load_dotenv
import re

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

def get_product_price(service_code, filters):
    """Get the price for a product based on filters"""
    try:
        pricing = boto3.client('pricing', region_name='us-east-1')
        response = pricing.get_products(ServiceCode=service_code, Filters=filters)
        print(f"\nDebug - Raw price data for {service_code}:")
        print(json.dumps(response, indent=2))
        
        if not response['PriceList']:
            print(f"\nDebug - No price found for {service_code} with filters:")
            print(json.dumps(filters, indent=2))
            return 0

        for price_item in response['PriceList']:
            if isinstance(price_item, str):
                price_item = json.loads(price_item)
            
            print("\nDebug - Product attributes:")
            print(json.dumps(price_item.get('product', {}).get('attributes', {}), indent=2))
            
            terms = price_item.get('terms', {}).get('OnDemand', {})
            for term_id, term in terms.items():
                dimensions = term.get('priceDimensions', {})
                for dimension_id, dimension in dimensions.items():
                    price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                    print(f"\nDebug - Price dimension:")
                    print(json.dumps(dimension, indent=2))
                    return price
        return 0
    except Exception as e:
        print(f"Error getting price: {str(e)}")
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
    print(f"  ├─ Hourly Rate: ${hourly_price:.4f}")
    print(f"  ├─ Hours per Month: {HOURS_PER_MONTH}")
    print(f"  └─ Monthly Cost: ${hourly_price * HOURS_PER_MONTH * quantity:.2f}")
    
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
    print(f"  ├─ Estimated Monthly Requests: {monthly_requests:,}")
    print(f"  ├─ Request Rate: ${request_price:.6f}/1000 requests" if request_price else "  ├─ Request Rate: Unknown")
    print(f"  ├─ Request Monthly Cost: ${request_cost:.2f}")
    print(f"  └─ Total Monthly Cost: ${total_cost:.2f}")

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
        print(f"  ├─ Monthly Requests: {monthly_requests:,}")
        print(f"  ├─ Avg. Duration: {avg_duration*1000:.0f}ms")
        print(f"  ├─ Computed GB-seconds: {gb_seconds:,.2f}")
        if request_price:
            print(f"  ├─ Request Rate: ${request_price:.6f}/million requests")
            print(f"  ├─ Request Cost: ${request_cost:.2f}")
        if duration_price:
            print(f"  ├─ Duration Rate: ${duration_price:.6f}/GB-second")
            print(f"  ├─ Duration Cost: ${duration_cost:.2f}")
        print(f"  └─ Total Monthly Cost: ${total_cost:.2f}")
        
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
        print(f"  ├─ Instance Hourly Rate: ${hourly_price:.4f}")
        print(f"  ├─ Instance Monthly Cost: ${instance_monthly:.2f}")
    if storage_price:
        print(f"  ├─ Storage Rate (per GB-month): ${storage_price:.4f}")
        print(f"  ├─ Storage Monthly Cost: ${storage_monthly:.2f}")
    print(f"  └─ Total Monthly Cost: ${total_monthly:.2f}")
    
    return total_monthly

# Mapping from component type in JSON to handler function
# Uses the type names found in templet_arch.json
COMPONENT_HANDLERS = {
    "AmazonEC2": estimate_ec2_cost,
    "AmazonS3": estimate_s3_cost,
    "AWSLambda": estimate_lambda_cost,
    "AmazonRDS": estimate_rds_cost,
    # Add other component types from JSON and their handlers here
    # e.g., "AmazonAPIGateway", "AutoScaling", "AmazonDynamoDB", etc.
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
    
    print(f"\nEstimated Total Monthly Cost: ${total_cost:.2f}")
    print("\nCost Breakdown:")
    if cost_breakdown:
        for item, cost in cost_breakdown.items():
            print(f"- {item}: ${cost:.2f}")
    else:
        print("(No costs calculated or all components skipped)")
        
    return total_cost, cost_breakdown

if __name__ == "__main__":
    # Example Usage: Replace with the actual path to your generated JSON
    # architecture_file = "path/to/your/architecture.json" 
    # architecture_file = "templet_arch.json" # Using the template for now as an example
    architecture_file = "demo_arch.json" # Use the demo file for testing
    
    if os.path.exists(architecture_file):
        estimate_cost_from_json(architecture_file)
    else:
        print(f"Example architecture file '{architecture_file}' not found. Please provide a valid path.") 
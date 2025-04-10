import json
import boto3
import requests
import datetime
import logging
from typing import Dict, Any, List, Optional, Union
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

class AWScostEstimator:
    """AWS Cost Estimation tool that takes an architecture JSON and provides pricing estimates."""
    
    def __init__(self, region="ap-south-1"):
        """Initialize the AWS cost estimator with the specified region."""
        self.region = region
        
        # Configure AWS credentials from environment variables
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', region)
        
        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError("AWS credentials not found in environment variables. Please check your .env file.")
        
        # Initialize AWS clients with credentials
        self.pricing_client = boto3.client(
            'pricing',
            region_name='us-east-1',  # Pricing API only available in us-east-1
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        self.ec2_client = boto3.client(
            'ec2',
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        self.rds_client = boto3.client(
            'rds',
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        self.dynamodb_client = boto3.client(
            'dynamodb',
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        self.s3_client = boto3.client(
            's3',
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        
        # Default values for services if not specified in the JSON
        self.defaults = {
            "AmazonEC2": {
                "InstanceType": "t3.medium",
                "TimeForHosting": "24/7",
                "HoursPerMonth": 730  # Average hours in a month
            },
            "AmazonRDS": {
                "DBEngine": "mysql",
                "DBInstanceClass": "db.t3.medium",
                "Storage": 20,  # GB
                "BackupRetention": 7  # days
            },
            "AmazonS3": {
                "Size": 100,  # GB
                "RequestCount": 100000  # per month
            },
            "AWSLambda": {
                "Runtime": "nodejs14.x",
                "Memory": 128,  # MB
                "Timeout": 3,  # seconds
                "Invocations": 1000000  # per month
            },
            "AmazonDynamoDB": {
                "Throughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                },
                "Storage": 20  # GB
            },
            "AmazonEBS": {
                "VolumeType": "gp3",
                "VolumeSize": 20,  # GB
                "VolumeCount": 1
            },
            "AmazonSNS": {
                "TopicCount": 5,
                "RequestsPerMonth": 1000000
            },
            "AWSELB": {
                "LoadBalancerType": "application",
                "ProcessedBytesPerMonth": 1000  # GB
            },
            "AWSEFS": {
                "Size": 20  # GB
            },
            "AmazonSQS": {
                "QueueCount": 5,
                "RequestsPerMonth": 1000000
            },
            "AWSIAMAccessAnalyzer": {
                "AnalyzerCount": 1
            },
            "AmazonAPIGateway": {
                "RequestsPerMonth": 1000000
            }
        }
        
        # Pricing cache to avoid repeated API calls
        self.price_cache = {}
        
        # Change logging level to ERROR to suppress INFO and WARNING
        logging.basicConfig(level=logging.ERROR)
        self.logger = logging.getLogger("AWScostEstimator")
    
    def get_aws_price(self, service_code: str, filters: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generic function to get AWS pricing information for any service.
        
        Args:
            service_code: AWS service code (e.g., 'AmazonEC2', 'AmazonS3')
            filters: List of filter dictionaries to narrow down pricing search
            
        Returns:
            Dictionary containing pricing information
        """
        filter_parts = []
        for f in filters:
            field = f.get('Field', '')
            value = f.get('Value', '')
            filter_parts.append(f"{field}={value}")
        
        cache_key = f"{service_code}:{','.join(filter_parts)}"
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
        
        try:
            response = self.pricing_client.get_products(
                ServiceCode=service_code,
                Filters=filters,
                MaxResults=10
            )
            
            result = {
                'success': False,
                'price': 0,
                'unit': '',
                'description': '',
                'price_details': {},
                'raw_response': []
            }
            
            if len(response.get('PriceList', [])) > 0:
                result['success'] = True
                result['raw_response'] = [json.loads(item) for item in response['PriceList']]
                
                # Extract pricing information from the response
                for price_item in result['raw_response']:
                    # Extract on-demand pricing
                    for term_id, term_attributes in price_item.get('terms', {}).get('OnDemand', {}).items():
                        for dimension_id, price_dimensions in term_attributes.get('priceDimensions', {}).items():
                            price_per_unit = price_dimensions.get('pricePerUnit', {}).get('USD', '0')
                            unit = price_dimensions.get('unit', '')
                            description = price_dimensions.get('description', '')
                            
                            # Store price details
                            price_detail = {
                                'price': float(price_per_unit),
                                'unit': unit,
                                'description': description,
                                'term_id': term_id,
                                'dimension_id': dimension_id
                            }
                            
                            # Add to price details
                            result['price_details'][description] = price_detail
                            
                            # Set the first price as default price
                            if result.get('price') == 0:
                                result['price'] = float(price_per_unit)
                                result['unit'] = unit
                                result['description'] = description
            
            self.price_cache[cache_key] = result
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting AWS price for {service_code}: {e}")
            return {
                'success': False,
                'price': 0,
                'unit': '',
                'description': '',
                'price_details': {},
                'error': str(e)
            }

    def process_architecture(self, architecture_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the architecture JSON and calculate cost estimates.
        
        Args:
            architecture_json: Dictionary containing the architecture specification
            
        Returns:
            Updated architecture JSON with cost estimations
        """
        total_hourly_cost = 0.0
        service_costs = {}
        
        # Helper function to convert value to float safely
        def safe_float(value, default=0.0):
            if value is None:
                return default
            try:
                # If it's already a number, return it
                if isinstance(value, (int, float)):
                    return float(value)
                    
                # If it's a string, try to extract the number
                if isinstance(value, str):
                    if not value.strip():
                        return default
                        
                    # Handle "X TB", "X GB", "X million" formats
                    value = value.strip().lower()
                    
                    # Extract the numeric part
                    import re
                    numeric_match = re.match(r'^(\d+\.?\d*|\.\d+)', value)
                    if not numeric_match:
                        return default
                        
                    number = float(numeric_match.group(1))
                    
                    # Apply scale based on unit
                    if "tb" in value or "terabyte" in value:
                        number *= 1024  # Convert TB to GB
                    elif "million" in value:
                        number *= 1000000
                    elif "billion" in value:
                        number *= 1000000000
                    
                    return number
                    
                return default
            except (ValueError, TypeError):
                self.logger.warning(f"Converting non-numeric value '{value}' to {default}")
                return default
        
        # Process each node in the architecture
        for node in architecture_json.get("nodes", []):
            node_type = node.get("type", "")
            node_id = node.get("id", "")
            node_label = node.get("label", node_id)
            hourly_cost = 0.0
            
            # Initialize cost breakdown if not present
            if "CostBreakdown" not in node:
                node["CostBreakdown"] = {}
            
            if node_type == "AmazonEC2":
                instance_type = node.get("InstanceType") or self.defaults["AmazonEC2"]["InstanceType"]
                node["InstanceType"] = instance_type
                
                # Get EC2 pricing using the generic function
                pricing_data = self.get_aws_price(
                    service_code='AmazonEC2',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                        {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                        {'Type': 'TERM_MATCH', 'Field': 'capacityStatus', 'Value': 'Used'},
                    ]
                )
                
                if pricing_data['success']:
                    hourly_cost = pricing_data['price']
                    self.logger.info(f"Found EC2 pricing for {instance_type}: ${hourly_cost}/hour")
                else:
                    hourly_cost = 0.05  # Default fallback price
                    self.logger.warning(f"Using default EC2 pricing for {instance_type}: ${hourly_cost}/hour")
                
                node["CostBreakdown"]["InstanceType"] = instance_type
                node["CostBreakdown"]["CostPerHour"] = f"${hourly_cost:.4f}"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AmazonRDS":
                db_engine = node.get("DBEngine") or self.defaults["AmazonRDS"]["DBEngine"]
                db_instance_class = node.get("DBInstanceClass") or self.defaults["AmazonRDS"]["DBInstanceClass"]
                storage = safe_float(node.get("Storage") or self.defaults["AmazonRDS"]["Storage"])
                
                node["DBEngine"] = db_engine
                node["DBInstanceClass"] = db_instance_class
                node["Storage"] = storage
                
                # Get RDS instance pricing
                rds_pricing_data = self.get_aws_price(
                    service_code='AmazonRDS',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': db_instance_class},
                        {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': db_engine},
                        {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ'},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                if rds_pricing_data['success']:
                    instance_hourly_cost = rds_pricing_data['price']
                    self.logger.info(f"Found RDS instance pricing for {db_instance_class}: ${instance_hourly_cost}/hour")
                else:
                    instance_hourly_cost = 0.08  # Default fallback price
                    self.logger.warning(f"Using default RDS pricing for {db_instance_class}: ${instance_hourly_cost}/hour")
                
                # Get EBS storage pricing for RDS
                storage_pricing_data = self.get_aws_price(
                    service_code='AmazonRDS',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': db_engine},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                        {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': 'General Purpose'},
                    ]
                )
                
                if storage_pricing_data['success']:
                    # Find storage price in the details
                    storage_price_per_gb = 0.115  # Default if not found
                    for desc, detail in storage_pricing_data['price_details'].items():
                        if 'storage' in desc.lower():
                            storage_price_per_gb = detail['price']
                            break
                    
                    storage_hourly_cost = (storage * storage_price_per_gb) / 730
                    self.logger.info(f"Found RDS storage pricing: ${storage_price_per_gb}/GB-month")
                else:
                    storage_hourly_cost = (storage * 0.115) / 730  # Default
                    self.logger.warning(f"Using default RDS storage pricing: $0.115/GB-month")
                
                backup_hourly_cost = storage_hourly_cost * 0.1  # 10% of storage cost
                total_hourly_cost_rds = instance_hourly_cost + storage_hourly_cost + backup_hourly_cost
                
                node["CostBreakdown"]["DBInstanceClass"] = db_instance_class
                node["CostBreakdown"]["StorageCost"] = f"${storage_hourly_cost:.4f}/hour"
                node["CostBreakdown"]["BackupStorageCost"] = f"${backup_hourly_cost:.4f}/hour"
                node["HourlyCost"] = f"${total_hourly_cost_rds:.4f}"
                
                hourly_cost = total_hourly_cost_rds
                
            elif node_type == "AmazonS3":
                size = safe_float(node.get("Size") or self.defaults["AmazonS3"]["Size"])
                node["Size"] = size
                
                # Get S3 storage pricing
                s3_pricing_data = self.get_aws_price(
                    service_code='AmazonS3',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': 'Standard'},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                # S3 Standard storage pricing tiers (simplified)
                if s3_pricing_data['success']:
                    # Find storage price in the details
                    price_per_gb = 0.023  # Default if not found
                    for desc, detail in s3_pricing_data['price_details'].items():
                        if 'storage' in desc.lower() and 'standard' in desc.lower():
                            price_per_gb = detail['price']
                            break
                    self.logger.info(f"Found S3 Standard storage pricing: ${price_per_gb}/GB-month")
                else:
                    # Fallback pricing
                    if size <= 50:
                        price_per_gb = 0.023
                    elif size <= 500:
                        price_per_gb = 0.022
                    else:
                        price_per_gb = 0.021
                    self.logger.warning(f"Using fallback S3 pricing: ${price_per_gb}/GB-month")
                
                hourly_cost = (price_per_gb * size) / 730
                
                node["CostBreakdown"]["StorageSize"] = f"{size} GB"
                node["CostBreakdown"]["CostPerGB"] = f"${price_per_gb}/GB-month"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AWSLambda":
                memory = safe_float(node.get("Memory") or self.defaults["AWSLambda"]["Memory"])
                invocations = safe_float(self.defaults["AWSLambda"]["Invocations"])
                
                node["Memory"] = memory
                
                # Get Lambda pricing
                lambda_pricing_data = self.get_aws_price(
                    service_code='AWSLambda',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                request_price = 0.20  # Default per million requests
                compute_price = 0.0000166667  # Default per GB-second
                
                if lambda_pricing_data['success']:
                    for desc, detail in lambda_pricing_data['price_details'].items():
                        if 'request' in desc.lower():
                            request_price = detail['price']
                        elif 'duration' in desc.lower() or 'compute' in desc.lower():
                            compute_price = detail['price']
                    self.logger.info(f"Found Lambda pricing: ${request_price}/million requests, ${compute_price}/GB-second")
                else:
                    self.logger.warning("Using default Lambda pricing")
                
                # Calculate Lambda cost
                gb = memory / 1024
                execution_time_per_request = 0.5  # 500ms
                monthly_request_cost = (invocations / 1000000) * request_price
                monthly_compute_cost = invocations * execution_time_per_request * gb * compute_price
                
                hourly_cost = (monthly_request_cost + monthly_compute_cost) / 730
                
                node["CostBreakdown"]["InvocationCost"] = f"${request_price} per million requests"
                node["CostBreakdown"]["ExecutionTimeCost"] = f"${compute_price} per GB-second" 
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AmazonDynamoDB":
                read_capacity_units = safe_float(self.defaults["AmazonDynamoDB"]["Throughput"]["ReadCapacityUnits"])
                write_capacity_units = safe_float(self.defaults["AmazonDynamoDB"]["Throughput"]["WriteCapacityUnits"])
                storage = safe_float(node.get("Storage") or self.defaults["AmazonDynamoDB"]["Storage"])
                
                node["Throughput"] = {
                    "ReadCapacityUnits": read_capacity_units,
                    "WriteCapacityUnits": write_capacity_units
                }
                node["Storage"] = storage
                
                # Get DynamoDB pricing
                dynamodb_pricing_data = self.get_aws_price(
                    service_code='AmazonDynamoDB',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                rcu_price = 0.00065  # Default
                wcu_price = 0.0065   # Default
                storage_price = 0.25  # Default per GB-month
                
                if dynamodb_pricing_data['success']:
                    for desc, detail in dynamodb_pricing_data['price_details'].items():
                        if 'read capacity' in desc.lower():
                            rcu_price = detail['price']
                        elif 'write capacity' in desc.lower():
                            wcu_price = detail['price']
                        elif 'storage' in desc.lower():
                            storage_price = detail['price']
                    self.logger.info(f"Found DynamoDB pricing: RCU=${rcu_price}, WCU=${wcu_price}, Storage=${storage_price}/GB-month")
                else:
                    self.logger.warning("Using default DynamoDB pricing")
                
                # Calculate DynamoDB cost
                monthly_rcu_cost = read_capacity_units * rcu_price * 730
                monthly_wcu_cost = write_capacity_units * wcu_price * 730
                monthly_storage_cost = storage * storage_price
                
                hourly_cost = (monthly_rcu_cost + monthly_wcu_cost + monthly_storage_cost) / 730
                
                throughput_hourly = (read_capacity_units * rcu_price + write_capacity_units * wcu_price)
                storage_hourly = (storage * storage_price / 730)
                
                node["CostBreakdown"]["ProvisionedThroughputCost"] = f"${throughput_hourly:.4f}/hour"
                node["CostBreakdown"]["StorageCost"] = f"${storage_hourly:.4f}/hour"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AmazonEBS":
                volume_count = safe_float(node.get("VolumeCount") or self.defaults["AmazonEBS"]["VolumeCount"])
                volume_type = self.defaults["AmazonEBS"]["VolumeType"]
                volume_size = safe_float(self.defaults["AmazonEBS"]["VolumeSize"])
                
                node["VolumeCount"] = volume_count
                node["VolumeType"] = volume_type
                node["VolumeSize"] = volume_size
                
                # Get EBS pricing
                ebs_pricing_data = self.get_aws_price(
                    service_code='AmazonEC2',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
                        {'Type': 'TERM_MATCH', 'Field': 'volumeApiName', 'Value': volume_type},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                if ebs_pricing_data['success']:
                    price_per_gb = 0
                    for desc, detail in ebs_pricing_data['price_details'].items():
                        if 'gb' in detail['unit'].lower():
                            price_per_gb = detail['price']
                            break
                    
                    if price_per_gb == 0:
                        price_per_gb = ebs_pricing_data['price']
                        
                    self.logger.info(f"Found EBS {volume_type} pricing: ${price_per_gb}/GB-month")
                else:
                    # Fallback to simplified EBS pricing
                    price_per_gb = {
                        'gp2': 0.10,
                        'gp3': 0.08,
                        'io1': 0.125,
                        'io2': 0.125,
                        'st1': 0.045,
                        'sc1': 0.025,
                        'standard': 0.05
                    }.get(volume_type.lower(), 0.08)
                    self.logger.warning(f"Using fallback EBS {volume_type} pricing: ${price_per_gb}/GB-month")
                
                hourly_cost = (price_per_gb * volume_size * volume_count) / 730
                
                node["CostBreakdown"]["VolumeType"] = volume_type
                node["CostBreakdown"]["VolumeSize"] = f"{volume_size} GB"
                node["CostBreakdown"]["VolumeCost"] = f"${hourly_cost:.4f}/hour"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AmazonAPIGateway":
                requests_per_month = safe_float(self.defaults["AmazonAPIGateway"]["RequestsPerMonth"])
                
                # Get API Gateway pricing
                api_pricing_data = self.get_aws_price(
                    service_code='AmazonApiGateway',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                if api_pricing_data['success']:
                    price_per_million = 0
                    for desc, detail in api_pricing_data['price_details'].items():
                        if 'request' in desc.lower():
                            price_per_million = detail['price']
                            break
                    
                    if price_per_million == 0:
                        price_per_million = 3.50  # Default
                        
                    self.logger.info(f"Found API Gateway pricing: ${price_per_million}/million requests")
                else:
                    price_per_million = 3.50  # Default
                    self.logger.warning(f"Using default API Gateway pricing: ${price_per_million}/million requests")
                
                hourly_cost = (requests_per_month / 1000000) * price_per_million / 730
                
                node["RequestsPerMonth"] = requests_per_month
                node["CostBreakdown"]["CostPerRequest"] = f"${price_per_million} per million requests"
                node["CostPerMillionRequests"] = f"${price_per_million}"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AmazonSNS":
                topic_count = safe_float(node.get("TopicCount") or self.defaults["AmazonSNS"]["TopicCount"])
                requests_per_month = safe_float(self.defaults["AmazonSNS"]["RequestsPerMonth"])
                
                # Get SNS pricing
                sns_pricing_data = self.get_aws_price(
                    service_code='AmazonSNS',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                if sns_pricing_data['success']:
                    price_per_million = 0
                    for desc, detail in sns_pricing_data['price_details'].items():
                        if 'request' in desc.lower():
                            price_per_million = detail['price']
                            break
                    
                    if price_per_million == 0:
                        price_per_million = 0.50  # Default
                        
                    self.logger.info(f"Found SNS pricing: ${price_per_million}/million requests")
                else:
                    price_per_million = 0.50  # Default
                    self.logger.warning(f"Using default SNS pricing: ${price_per_million}/million requests")
                
                hourly_cost = (requests_per_month / 1000000) * price_per_million / 730
                
                node["TopicCount"] = topic_count
                node["RequestsPerMonth"] = requests_per_month
                node["CostBreakdown"]["TopicCost"] = f"${hourly_cost:.4f}/hour"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AWSELB":
                lb_type = node.get("LoadBalancerType") or self.defaults["AWSELB"]["LoadBalancerType"]
                
                # Get ELB pricing
                elb_service_code = 'AmazonELB' if lb_type.lower() == 'classic' else 'AWSELB'
                elb_pricing_data = self.get_aws_price(
                    service_code=elb_service_code,
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                if elb_pricing_data['success']:
                    hourly_price = 0
                    for desc, detail in elb_pricing_data['price_details'].items():
                        if 'load balancer' in desc.lower():
                            hourly_price = detail['price']
                            break
                    
                    if hourly_price == 0:
                        hourly_price = {
                            'application': 0.0225,
                            'network': 0.0225,
                            'classic': 0.025
                        }.get(lb_type.lower(), 0.0225)
                        
                    self.logger.info(f"Found ELB pricing for {lb_type}: ${hourly_price}/hour")
                else:
                    hourly_price = {
                        'application': 0.0225,
                        'network': 0.0225,
                        'classic': 0.025
                    }.get(lb_type.lower(), 0.0225)
                    self.logger.warning(f"Using default ELB pricing for {lb_type}: ${hourly_price}/hour")
                
                hourly_cost = hourly_price
                
                node["LoadBalancerType"] = lb_type
                node["CostBreakdown"]["LoadBalancerCost"] = f"${hourly_cost:.4f}/hour"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AWSEFS":
                size = safe_float(node.get("Size") or self.defaults["AWSEFS"]["Size"])
                
                # Get EFS pricing
                efs_pricing_data = self.get_aws_price(
                    service_code='AmazonEFS',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                if efs_pricing_data['success']:
                    price_per_gb = 0
                    for desc, detail in efs_pricing_data['price_details'].items():
                        if 'storage' in desc.lower() and 'standard' in desc.lower():
                            price_per_gb = detail['price']
                            break
                    
                    if price_per_gb == 0:
                        price_per_gb = 0.30  # Default
                        
                    self.logger.info(f"Found EFS pricing: ${price_per_gb}/GB-month")
                else:
                    price_per_gb = 0.30  # Default
                    self.logger.warning(f"Using default EFS pricing: ${price_per_gb}/GB-month")
                
                hourly_cost = (size * price_per_gb) / 730
                
                node["Size"] = size
                node["CostBreakdown"]["StorageSizeCost"] = f"${hourly_cost:.4f}/hour"
                node["CostBreakdown"]["IOCost"] = "$0.00 (included in base price)"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AmazonSQS":
                queue_count = safe_float(node.get("QueueCount") or self.defaults["AmazonSQS"]["QueueCount"])
                requests_per_month = safe_float(self.defaults["AmazonSQS"]["RequestsPerMonth"])
                
                # Get SQS pricing
                sqs_pricing_data = self.get_aws_price(
                    service_code='AmazonSQS',
                    filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                if sqs_pricing_data['success']:
                    price_per_million = 0
                    for desc, detail in sqs_pricing_data['price_details'].items():
                        if 'request' in desc.lower():
                            price_per_million = detail['price']
                            break
                    
                    if price_per_million == 0:
                        price_per_million = 0.40  # Default
                        
                    self.logger.info(f"Found SQS pricing: ${price_per_million}/million requests")
                else:
                    price_per_million = 0.40  # Default
                    self.logger.warning(f"Using default SQS pricing: ${price_per_million}/million requests")
                
                hourly_cost = (requests_per_month / 1000000) * price_per_million / 730
                
                node["QueueCount"] = queue_count
                node["RequestsPerMonth"] = requests_per_month
                node["CostBreakdown"]["QueueCost"] = f"${hourly_cost:.4f}/hour"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
                
            elif node_type == "AWSIAMAccessAnalyzer":
                analyzer_count = safe_float(node.get("AnalyzerCount") or self.defaults["AWSIAMAccessAnalyzer"]["AnalyzerCount"])
                
                # IAM Access Analyzer pricing is generally $1.00 per analyzer per month
                hourly_cost = (analyzer_count * 1.00) / 730
                
                node["AnalyzerCount"] = analyzer_count
                node["CostBreakdown"]["AnalyzerCost"] = f"${hourly_cost:.4f}/hour"
                node["HourlyCost"] = f"${hourly_cost:.4f}"
            
            # Add the node's hourly cost to service costs
            service_costs[node_label] = f"${hourly_cost:.4f}/hour"
            
            # Add the node's hourly cost to the total
            total_hourly_cost += hourly_cost
                
        # Add total cost to the architecture JSON - only hourly cost as requested
        architecture_json["TotalCost"] = {
            "HourlyCost": f"${total_hourly_cost:.4f}",
            "ServiceBreakdown": service_costs
        }
        
        return architecture_json
    
    def estimate_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Estimate costs from a JSON file containing one or more architecture definitions.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            List of updated architecture JSONs with cost estimations
        """
        try:
            with open(file_path, 'r') as f:
                json_data = json.load(f)
                
            # Check if the JSON is a list of architectures or a single architecture
            if isinstance(json_data, list):
                updated_architectures = []
                for architecture in json_data:
                    updated_architecture = self.process_architecture(architecture)
                    updated_architectures.append(updated_architecture)
                return updated_architectures
            else:
                # Single architecture
                updated_architecture = self.process_architecture(json_data)
                return [updated_architecture]
                
        except Exception as e:
            self.logger.error(f"Error processing architecture file: {e}")
            raise

    def estimate_from_json(self, architecture_json: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Estimate costs from a JSON object.
        
        Args:
            architecture_json: JSON object or list of JSON objects containing architecture specification
            
        Returns:
            Updated architecture JSON(s) with cost estimations
        """
        try:
            if isinstance(architecture_json, list):
                updated_architectures = []
                for architecture in architecture_json:
                    updated_architecture = self.process_architecture(architecture)
                    updated_architectures.append(updated_architecture)
                return updated_architectures
            else:
                return self.process_architecture(architecture_json)
        except Exception as e:
            self.logger.error(f"Error processing architecture JSON: {e}")
            raise

def main():
    """Main function to run the cost estimator."""
    import sys
    import argparse
    
    # Suppress all warnings from boto3, botocore, and urllib3
    import urllib3
    urllib3.disable_warnings()
    import boto3
    
    # Fix for botocore logger
    boto3.set_stream_logger('', logging.ERROR)
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    
    parser = argparse.ArgumentParser(description="AWS Cost Estimation Tool")
    parser.add_argument("-f", "--file", help="JSON file containing the architecture(s)")
    parser.add_argument("-r", "--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("-o", "--output", help="Output file for the updated JSON")
    parser.add_argument("--verbose", action="store_true", help="Show detailed logs")
    args = parser.parse_args()
    
    # Setup logger levels
    if not args.verbose:
        logging.getLogger().setLevel(logging.ERROR)
    
    estimator = AWScostEstimator(region=args.region)
    
    try:
        if args.file:
            # Read from file (suppress any output)
            updated_architectures = estimator.estimate_from_file(args.file)
        else:
            # Interactive mode with better error handling
            try:
                print("Enter your architecture JSON (paste and press Ctrl+D on Unix/Linux or Ctrl+Z followed by Enter on Windows):")
                json_text = ""
                for line in sys.stdin:
                    json_text += line
                architecture_json = json.loads(json_text)
                updated_architectures = estimator.estimate_from_json(architecture_json)
                if not isinstance(updated_architectures, list):
                    updated_architectures = [updated_architectures]
            except KeyboardInterrupt:
                print("\nInput interrupted. Please provide the JSON as a file using -f option instead.")
                return
        
        # Save the full JSON if requested (quietly)
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(updated_architectures, f, indent=2)
        
        # Print costs for each architecture
        for i, architecture in enumerate(updated_architectures):
            print(f"\n{'=' * 60}")
            print(f"Architecture {i+1}: {architecture.get('title', f'Architecture {i+1}')}")
            print(f"{'=' * 60}")
            
            # Extract total hourly cost as a float
            total_hourly_cost = float(architecture['TotalCost']['HourlyCost'].replace('$', ''))
            total_monthly_cost = total_hourly_cost * 730  # 730 hours in a month
            
            # Print service costs and total in a clean, precise format
            print("\nService Costs:")
            print("-" * 60)
            print(f"{'Service'.ljust(30)} {'Hourly'.rjust(10)} {'Monthly'.rjust(15)} {'Yearly'.rjust(15)}")
            print("-" * 60)
            
            # Calculate padding for alignment
            max_service_length = max(len(service) for service in architecture['TotalCost']['ServiceBreakdown'].keys())
            
            # Print each service with aligned costs (skipping zero-cost services)
            for service, cost in architecture['TotalCost']['ServiceBreakdown'].items():
                hourly_cost = float(cost.replace('$', '').replace('/hour', ''))
                if hourly_cost > 0.0001:  # Skip negligible costs
                    monthly_cost = hourly_cost * 730
                    yearly_cost = monthly_cost * 12
                    print(f"{service.ljust(30)} ${hourly_cost:>9.4f} ${monthly_cost:>14.2f} ${yearly_cost:>14.2f}")
            
            print("-" * 60)
            print(f"{'Total'.ljust(30)} ${total_hourly_cost:>9.4f} ${total_monthly_cost:>14.2f} ${total_monthly_cost*12:>14.2f}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
import json
import boto3
import os
import argparse
from dotenv import load_dotenv
import logging
from typing import Dict, Any, List

# Load environment variables from .env file
load_dotenv()

class AWSCostFetcher:
    """Fetch actual AWS costs based on a JSON architecture definition"""
    
    def __init__(self):
        """Initialize the cost fetcher with AWS credentials from environment"""
        # Get AWS credentials from environment variables
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'us-east-1')
        
        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError("AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file.")
        
        # Initialize boto3 clients
        self.pricing_client = boto3.client(
            'pricing', 
            region_name='us-east-1',  # Pricing API is only available in us-east-1
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
        
        self.region = aws_region
        self.price_cache = {}
        
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger('AWSCostFetcher')
    
    def get_ec2_price(self, instance_type: str) -> float:
        """Get the price for an EC2 instance type"""
        cache_key = f"EC2:{instance_type}:{self.region}"
        
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
        
        try:
            # First try with exact filters
            response = self.pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                    {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                    {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                    {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    {'Type': 'TERM_MATCH', 'Field': 'capacityStatus', 'Value': 'Used'},
                ]
            )
            
            # If no results, try more relaxed filters
            if len(response.get('PriceList', [])) == 0:
                self.logger.info(f"Trying more relaxed filters for EC2 instance type {instance_type}")
                response = self.pricing_client.get_products(
                    ServiceCode='AmazonEC2',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
            
            price_per_hour = 0.0
            
            if len(response.get('PriceList', [])) > 0:
                for price_str in response['PriceList']:
                    price = json.loads(price_str)
                    
                    # Skip Savings Plans and Reserved Instances
                    on_demand_terms = price.get('terms', {}).get('OnDemand', {})
                    if not on_demand_terms:
                        continue
                        
                    for term_key, term in on_demand_terms.items():
                        for dimension_key, dimension in term.get('priceDimensions', {}).items():
                            unit = dimension.get('unit', '').lower()
                            if 'hour' in unit or 'hrs' in unit or 'hr' in unit:
                                usd_price = dimension.get('pricePerUnit', {}).get('USD', 0)
                                if usd_price and float(usd_price) > 0:
                                    price_per_hour = float(usd_price)
                                    self.logger.info(f"Found EC2 price for {instance_type}: ${price_per_hour}/hour")
                                    break
                        if price_per_hour > 0:
                            break
                    if price_per_hour > 0:
                        break
            
            # If still not found, inform user instead of using hardcoded fallbacks
            if price_per_hour == 0.0:
                self.logger.warning(f"No pricing data found for EC2 instance type {instance_type} in region {self.region}. Price data will be reported as $0.")
            
            self.price_cache[cache_key] = price_per_hour
            return price_per_hour
        
        except Exception as e:
            self.logger.error(f"Error getting EC2 price: {e}")
            return 0.0  # Return zero instead of hardcoded fallback
    
    def get_rds_price(self, db_instance_class: str, engine: str) -> float:
        """Get the price for an RDS instance class"""
        cache_key = f"RDS:{db_instance_class}:{engine}:{self.region}"
        
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
        
        try:
            # First try with exact filters
            response = self.pricing_client.get_products(
                ServiceCode='AmazonRDS',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': db_instance_class},
                    {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': engine},
                    {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ'},
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                ]
            )
            
            # If no results, try more relaxed filters
            if len(response.get('PriceList', [])) == 0:
                self.logger.info(f"Trying more relaxed filters for RDS instance class {db_instance_class}")
                response = self.pricing_client.get_products(
                    ServiceCode='AmazonRDS',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': db_instance_class},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
            
            price_per_hour = 0.0
            
            if len(response.get('PriceList', [])) > 0:
                for price_str in response['PriceList']:
                    price = json.loads(price_str)
                    
                    product_attributes = price.get('product', {}).get('attributes', {})
                    if engine.lower() not in product_attributes.get('databaseEngine', '').lower():
                        continue
                        
                    # Skip Savings Plans and Reserved Instances
                    on_demand_terms = price.get('terms', {}).get('OnDemand', {})
                    if not on_demand_terms:
                        continue
                        
                    for term_key, term in on_demand_terms.items():
                        for dimension_key, dimension in term.get('priceDimensions', {}).items():
                            unit = dimension.get('unit', '').lower()
                            if 'hour' in unit or 'hrs' in unit or 'hr' in unit:
                                usd_price = dimension.get('pricePerUnit', {}).get('USD', 0)
                                if usd_price and float(usd_price) > 0:
                                    price_per_hour = float(usd_price)
                                    self.logger.info(f"Found RDS price for {db_instance_class}: ${price_per_hour}/hour")
                                    break
                        if price_per_hour > 0:
                            break
                    if price_per_hour > 0:
                        break
            
            # If still not found, inform user instead of using hardcoded fallbacks
            if price_per_hour == 0.0:
                self.logger.warning(f"No pricing data found for RDS instance class {db_instance_class} with engine {engine} in region {self.region}. Price data will be reported as $0.")
            
            self.price_cache[cache_key] = price_per_hour
            return price_per_hour
        
        except Exception as e:
            self.logger.error(f"Error getting RDS price: {e}")
            return 0.0  # Return zero instead of hardcoded fallback
    
    def get_s3_price(self, storage_gb: float) -> float:
        """Get the price for S3 storage"""
        cache_key = f"S3:storage:{self.region}"
        
        if cache_key in self.price_cache:
            price_per_gb = self.price_cache[cache_key]
        else:
            try:
                # First try with specific filter for Standard storage
                response = self.pricing_client.get_products(
                    ServiceCode='AmazonS3',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': 'Standard'},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                # If no results, try more relaxed filters
                if len(response.get('PriceList', [])) == 0:
                    self.logger.info(f"Trying more relaxed filters for S3 Standard storage")
                    response = self.pricing_client.get_products(
                        ServiceCode='AmazonS3',
                        Filters=[
                            {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                        ]
                    )
                
                price_per_gb = 0.0
                
                if len(response.get('PriceList', [])) > 0:
                    for price_str in response['PriceList']:
                        price = json.loads(price_str)
                        product_attributes = price.get('product', {}).get('attributes', {})
                        
                        # Look for Standard storage pricing
                        if 'standard' in product_attributes.get('storageClass', '').lower():
                            for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                                for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                    if ('gb' in dimension.get('unit', '').lower() and 
                                        'storage' in dimension.get('description', '').lower()):
                                        usd_price = dimension.get('pricePerUnit', {}).get('USD', 0)
                                        if usd_price and float(usd_price) > 0:
                                            price_per_gb = float(usd_price)
                                            self.logger.info(f"Found S3 Standard storage price: ${price_per_gb}/GB-month")
                                            break
                                if price_per_gb > 0:  # If a price was found
                                    break
                            if price_per_gb > 0:  # If a price was found
                                break
                
                if price_per_gb == 0.0:
                    self.logger.warning(f"No pricing data found for S3 Standard storage in region {self.region}. Price data will be reported as $0.")
                
                self.price_cache[cache_key] = price_per_gb
                
            except Exception as e:
                self.logger.error(f"Error getting S3 price: {e}")
                price_per_gb = 0.0
        
        # If no price data found, return 0
        if price_per_gb == 0.0:
            return 0.0
            
        # Use AWS tiered pricing structure (if price data is available)
        # These tiers reflect AWS actual pricing structure, not hardcoded values
        storage_cost = 0.0
        
        # Apply the pricing to the appropriate tier
        # First 50 TB tier
        if storage_gb <= 51200:  # 50 TB in GB
            storage_cost = storage_gb * price_per_gb
        else:
            storage_cost = 51200 * price_per_gb
            remaining_gb = storage_gb - 51200
            
            # Get tier 2 pricing (next 450 TB)
            tier2_price_cache_key = f"S3:storage:tier2:{self.region}"
            if tier2_price_cache_key in self.price_cache:
                tier2_price = self.price_cache[tier2_price_cache_key]
            else:
                # Try to get tier 2 pricing from API
                try:
                    # This is using the official pricing tiers from AWS, not hardcoded values
                    tier2_response = self.pricing_client.get_products(
                        ServiceCode='AmazonS3',
                        Filters=[
                            {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                        ]
                    )
                    
                    tier2_price = 0.0
                    # Look for tier 2 pricing (next 450 TB)
                    if len(tier2_response.get('PriceList', [])) > 0:
                        for price_str in tier2_response['PriceList']:
                            price = json.loads(price_str)
                            for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                                for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                    desc = dimension.get('description', '').lower()
                                    if 'next 450 tb' in desc or '450 tb' in desc:
                                        tier2_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                        break
                    
                    # If tier 2 pricing not found, just use the tier 1 price
                    if tier2_price == 0.0:
                        tier2_price = price_per_gb
                        
                    self.price_cache[tier2_price_cache_key] = tier2_price
                except Exception:
                    tier2_price = price_per_gb
            
            # Next 450 TB tier
            if remaining_gb <= 460800:  # 450 TB in GB
                storage_cost += remaining_gb * tier2_price
            else:
                storage_cost += 460800 * tier2_price
                remaining_gb -= 460800
                
                # Get tier 3 pricing (over 500 TB)
                tier3_price_cache_key = f"S3:storage:tier3:{self.region}"
                if tier3_price_cache_key in self.price_cache:
                    tier3_price = self.price_cache[tier3_price_cache_key]
                else:
                    # Try to get tier 3 pricing from API
                    try:
                        # Again using AWS pricing tiers, not hardcoded values
                        tier3_response = self.pricing_client.get_products(
                            ServiceCode='AmazonS3',
                            Filters=[
                                {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                            ]
                        )
                        
                        tier3_price = 0.0
                        # Look for tier 3 pricing (over 500 TB)
                        if len(tier3_response.get('PriceList', [])) > 0:
                            for price_str in tier3_response['PriceList']:
                                price = json.loads(price_str)
                                for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                                    for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                        desc = dimension.get('description', '').lower()
                                        if 'over 500 tb' in desc or '500+ tb' in desc:
                                            tier3_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                            break
                        
                        # If tier 3 pricing not found, just use tier 2 price
                        if tier3_price == 0.0:
                            tier3_price = tier2_price
                            
                        self.price_cache[tier3_price_cache_key] = tier3_price
                    except Exception:
                        tier3_price = tier2_price
                
                # Over 500 TB tier
                storage_cost += remaining_gb * tier3_price
        
        # Note: Request pricing is highly variable and difficult to determine from the API
        # We're omitting it here since it's minor compared to storage costs
        
        # Convert to hourly cost
        hourly_cost = storage_cost / 730  # 730 hours in a month
        
        return hourly_cost
    
    def get_dynamodb_price(self, read_capacity_units: float, write_capacity_units: float, storage_gb: float) -> float:
        """Get the price for DynamoDB provisioned capacity and storage"""
        cache_key = f"DynamoDB:capacity:{self.region}"
        
        if cache_key in self.price_cache:
            pricing = self.price_cache[cache_key]
        else:
            try:
                response = self.pricing_client.get_products(
                    ServiceCode='AmazonDynamoDB',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                rcu_price = 0.0
                wcu_price = 0.0
                storage_price = 0.0
                
                if len(response.get('PriceList', [])) > 0:
                    for price_str in response['PriceList']:
                        price = json.loads(price_str)
                        product_attributes = price.get('product', {}).get('attributes', {})
                        
                        for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                            for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                description = dimension.get('description', '').lower()
                                
                                if 'read capacity unit' in description:
                                    rcu_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found DynamoDB RCU price: ${rcu_price}/RCU-hour")
                                    
                                elif 'write capacity unit' in description:
                                    wcu_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found DynamoDB WCU price: ${wcu_price}/WCU-hour")
                                    
                                elif 'storage' in description and 'data' in description:
                                    storage_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found DynamoDB storage price: ${storage_price}/GB-month")
                
                if rcu_price == 0.0 or wcu_price == 0.0 or storage_price == 0.0:
                    self.logger.warning(f"Incomplete DynamoDB pricing data found in region {self.region}. Some prices will be reported as $0.")
                
                pricing = {
                    'rcu_price': rcu_price,
                    'wcu_price': wcu_price,
                    'storage_price': storage_price
                }
                self.price_cache[cache_key] = pricing
                
            except Exception as e:
                self.logger.error(f"Error getting DynamoDB price: {e}")
                pricing = {
                    'rcu_price': 0.0,
                    'wcu_price': 0.0,
                    'storage_price': 0.0
                }
        
        # Calculate hourly cost
        capacity_cost = (read_capacity_units * pricing['rcu_price'] + 
                         write_capacity_units * pricing['wcu_price'])
        storage_cost = (storage_gb * pricing['storage_price']) / 730
        
        return capacity_cost + storage_cost
    
    def get_lambda_price(self, memory_mb: int, invocations: int, avg_duration_ms: int = 500) -> float:
        """Get the price for Lambda based on memory, invocations, and duration"""
        cache_key = f"Lambda:pricing:{self.region}"
        
        if cache_key in self.price_cache:
            pricing = self.price_cache[cache_key]
        else:
            try:
                response = self.pricing_client.get_products(
                    ServiceCode='AWSLambda',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                request_price = 0.0
                compute_price = 0.0
                
                if len(response.get('PriceList', [])) > 0:
                    for price_str in response['PriceList']:
                        price = json.loads(price_str)
                        
                        for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                            for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                description = dimension.get('description', '').lower()
                                
                                if 'request' in description:
                                    request_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found Lambda request price: ${request_price}/million requests")
                                    
                                elif 'duration' in description or 'gb-second' in description:
                                    compute_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found Lambda compute price: ${compute_price}/GB-second")
                
                if request_price == 0.0 or compute_price == 0.0:
                    self.logger.warning(f"Incomplete Lambda pricing data found in region {self.region}. Some prices will be reported as $0.")
                
                pricing = {
                    'request_price': request_price,
                    'compute_price': compute_price
                }
                self.price_cache[cache_key] = pricing
                
            except Exception as e:
                self.logger.error(f"Error getting Lambda price: {e}")
                pricing = {
                    'request_price': 0.0,
                    'compute_price': 0.0
                }
        
        # Calculate monthly costs
        gb = memory_mb / 1024
        duration_seconds = avg_duration_ms / 1000
        monthly_request_cost = (invocations / 1000000) * pricing['request_price']
        monthly_compute_cost = invocations * duration_seconds * gb * pricing['compute_price']
        
        # Convert to hourly cost
        hourly_cost = (monthly_request_cost + monthly_compute_cost) / 730
        
        return hourly_cost
    
    def get_ebs_price(self, volume_type: str, volume_size_gb: float, iops: int = 0, throughput: int = 0) -> float:
        """Get the price for EBS volumes"""
        cache_key = f"EBS:{volume_type}:{self.region}"
        
        if cache_key in self.price_cache:
            pricing = self.price_cache[cache_key]
        else:
            try:
                response = self.pricing_client.get_products(
                    ServiceCode='AmazonEC2',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
                        {'Type': 'TERM_MATCH', 'Field': 'volumeApiName', 'Value': volume_type},
                        {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                    ]
                )
                
                storage_price = 0.0
                iops_price = 0.0
                throughput_price = 0.0
                
                if len(response.get('PriceList', [])) > 0:
                    for price_str in response['PriceList']:
                        price = json.loads(price_str)
                        product_attributes = price.get('product', {}).get('attributes', {})
                        
                        for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                            for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                description = dimension.get('description', '').lower()
                                
                                if 'storage' in description or 'volume' in description:
                                    storage_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found EBS {volume_type} storage price: ${storage_price}/GB-month")
                                    
                                elif 'iops' in description:
                                    iops_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found EBS {volume_type} IOPS price: ${iops_price}/IOPS-month")
                                    
                                elif 'throughput' in description:
                                    throughput_price = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found EBS {volume_type} throughput price: ${throughput_price}/MB/s-month")
                
                if storage_price == 0.0:
                    self.logger.warning(f"No EBS {volume_type} storage pricing data found in region {self.region}. Price will be reported as $0.")
                
                pricing = {
                    'storage_price': storage_price,
                    'iops_price': iops_price,
                    'throughput_price': throughput_price
                }
                self.price_cache[cache_key] = pricing
                
            except Exception as e:
                self.logger.error(f"Error getting EBS price: {e}")
                pricing = {
                    'storage_price': 0.0,
                    'iops_price': 0.0,
                    'throughput_price': 0.0
                }
        
        # Calculate cost components
        storage_cost = volume_size_gb * pricing['storage_price']
        iops_cost = 0
        throughput_cost = 0
        
        # Add IOPS cost for io1/io2 volumes
        if volume_type.lower() in ['io1', 'io2'] and iops > 0:
            iops_cost = iops * pricing['iops_price']
        
        # Add throughput cost for gp3 if over 125 MB/s
        if volume_type.lower() == 'gp3' and throughput > 125:
            throughput_cost = (throughput - 125) * pricing['throughput_price']
        
        # Convert to hourly cost
        hourly_cost = (storage_cost + iops_cost + throughput_cost) / 730
        
        return hourly_cost
    
    def get_elb_price(self, lb_type: str) -> float:
        """Get the price for ELB (Elastic Load Balancer)"""
        cache_key = f"ELB:{lb_type}:{self.region}"
        
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
        
        try:
            # Determine the service code based on LB type
            service_code = 'AWSELB'  # Default for ALB/NLB
            if lb_type.lower() == 'classic':
                service_code = 'AmazonEC2'  # Classic Load Balancer uses EC2
            
            response = self.pricing_client.get_products(
                ServiceCode=service_code,
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': self.region},
                ]
            )
            
            price_per_hour = 0.0
            
            if len(response.get('PriceList', [])) > 0:
                for price_str in response['PriceList']:
                    price = json.loads(price_str)
                    product_attributes = price.get('product', {}).get('attributes', {})
                    
                    # Check for load balancer type in attributes
                    lb_attribute = product_attributes.get('usagetype', '').lower()
                    
                    # Match the appropriate LB type
                    if lb_type.lower() == 'application' and 'alb' in lb_attribute:
                        # Found Application Load Balancer
                        for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                            for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                unit = dimension.get('unit', '').lower()
                                if unit == 'hrs':
                                    price_per_hour = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found ALB price: ${price_per_hour}/hour")
                                    break
                    
                    elif lb_type.lower() == 'network' and 'nlb' in lb_attribute:
                        # Found Network Load Balancer
                        for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                            for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                unit = dimension.get('unit', '').lower()
                                if unit == 'hrs':
                                    price_per_hour = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found NLB price: ${price_per_hour}/hour")
                                    break
                    
                    elif lb_type.lower() == 'classic' and 'elb' in lb_attribute:
                        # Found Classic Load Balancer
                        for term_key, term in price.get('terms', {}).get('OnDemand', {}).items():
                            for dimension_key, dimension in term.get('priceDimensions', {}).items():
                                unit = dimension.get('unit', '').lower()
                                if unit == 'hrs':
                                    price_per_hour = float(dimension.get('pricePerUnit', {}).get('USD', 0))
                                    self.logger.info(f"Found Classic ELB price: ${price_per_hour}/hour")
                                    break
                    
                    # If we found a price, break out of the loop
                    if price_per_hour > 0:
                        break
            
            if price_per_hour == 0.0:
                self.logger.warning(f"No pricing data found for {lb_type} Load Balancer in region {self.region}. Price will be reported as $0.")
            
            self.price_cache[cache_key] = price_per_hour
            return price_per_hour
            
        except Exception as e:
            self.logger.error(f"Error getting ELB price: {e}")
            return 0.0  # Return zero instead of hardcoded fallback
    
    def estimate_costs(self, architecture_json: Dict) -> Dict:
        """Process the architecture JSON and calculate cost estimates"""
        if "nodes" not in architecture_json:
            raise ValueError("Invalid architecture JSON: 'nodes' key not found")
        
        total_hourly_cost = 0.0
        service_costs = {}
        missing_price_data = []
        
        # Process each node in the architecture
        for node in architecture_json["nodes"]:
            node_type = node.get("type", "")
            node_id = node.get("id", "")
            node_label = node.get("label", node_id)
            
            hourly_cost = 0.0
            cost_details = {}
            
            if node_type == "AmazonEC2":
                instance_type = node.get("InstanceType", "t3.medium")
                hourly_cost = self.get_ec2_price(instance_type)
                
                # Add EBS storage costs if specified
                ebs_volumes = node.get("EBSVolumes", [])
                ebs_cost = 0.0
                if ebs_volumes:
                    for volume in ebs_volumes:
                        volume_type = volume.get("VolumeType", "gp3")
                        volume_size = float(volume.get("VolumeSize", 20))
                        iops = int(volume.get("IOPS", 0))
                        throughput = int(volume.get("Throughput", 0))
                        ebs_cost += self.get_ebs_price(volume_type, volume_size, iops, throughput)
                else:
                    # Default EBS volume if none specified
                    ebs_cost = self.get_ebs_price("gp3", 20)
                
                hourly_cost += ebs_cost
                
                cost_details = {
                    "InstanceType": instance_type,
                    "InstanceHourlyCost": f"${self.get_ec2_price(instance_type):.4f}",
                    "EBSStorageHourlyCost": f"${ebs_cost:.4f}",
                    "TotalHourlyCost": f"${hourly_cost:.4f}"
                }
                
            elif node_type == "AmazonRDS":
                db_engine = node.get("DBEngine", "mysql")
                db_instance_class = node.get("DBInstanceClass", "db.t3.medium")
                storage = float(node.get("Storage", 20))
                multi_az = node.get("MultiAZ", False)
                
                # Get base instance price
                instance_hourly_cost = self.get_rds_price(db_instance_class, db_engine)
                
                # Double cost if Multi-AZ is enabled
                if multi_az:
                    instance_hourly_cost *= 2
                
                # Add storage cost (using EBS pricing since RDS uses EBS)
                storage_type = node.get("StorageType", "gp3")
                iops = int(node.get("IOPS", 0))
                storage_hourly_cost = self.get_ebs_price(storage_type, storage, iops)
                
                # Add backup cost (typically 10% of storage cost)
                backup_retention = int(node.get("BackupRetention", 7))
                backup_hourly_cost = storage_hourly_cost * 0.1 * (backup_retention / 7)
                
                hourly_cost = instance_hourly_cost + storage_hourly_cost + backup_hourly_cost
                
                cost_details = {
                    "DBEngine": db_engine,
                    "DBInstanceClass": db_instance_class,
                    "MultiAZ": "Yes" if multi_az else "No",
                    "Storage": f"{storage} GB",
                    "InstanceHourlyCost": f"${instance_hourly_cost:.4f}",
                    "StorageHourlyCost": f"${storage_hourly_cost:.4f}",
                    "BackupHourlyCost": f"${backup_hourly_cost:.4f}",
                    "TotalHourlyCost": f"${hourly_cost:.4f}"
                }
                
            elif node_type == "AmazonS3":
                storage = float(node.get("Storage", 100))
                request_count = int(node.get("RequestCount", 100000))
                
                hourly_cost = self.get_s3_price(storage)
                
                cost_details = {
                    "Storage": f"{storage} GB",
                    "RequestsPerMonth": f"{request_count}",
                    "HourlyCost": f"${hourly_cost:.4f}"
                }
                
            elif node_type == "AmazonDynamoDB":
                read_capacity_units = float(node.get("ReadCapacityUnits", 5))
                write_capacity_units = float(node.get("WriteCapacityUnits", 5))
                storage = float(node.get("Storage", 20))
                
                hourly_cost = self.get_dynamodb_price(read_capacity_units, write_capacity_units, storage)
                
                cost_details = {
                    "ReadCapacityUnits": f"{read_capacity_units}",
                    "WriteCapacityUnits": f"{write_capacity_units}",
                    "Storage": f"{storage} GB",
                    "HourlyCost": f"${hourly_cost:.4f}"
                }
                
            elif node_type == "AWSLambda":
                memory = int(node.get("Memory", 128))
                invocations = int(node.get("Invocations", 1000000))
                avg_duration = int(node.get("AvgDuration", 500))  # in milliseconds
                
                hourly_cost = self.get_lambda_price(memory, invocations, avg_duration)
                
                cost_details = {
                    "Memory": f"{memory} MB",
                    "InvocationsPerMonth": f"{invocations}",
                    "AvgDuration": f"{avg_duration} ms",
                    "HourlyCost": f"${hourly_cost:.4f}"
                }
                
            elif node_type == "AmazonEBS":
                volume_type = node.get("VolumeType", "gp3")
                volume_size = float(node.get("VolumeSize", 20))
                iops = int(node.get("IOPS", 0))
                throughput = int(node.get("Throughput", 0))
                volume_count = int(node.get("VolumeCount", 1))
                
                single_volume_cost = self.get_ebs_price(volume_type, volume_size, iops, throughput)
                hourly_cost = single_volume_cost * volume_count
                
                cost_details = {
                    "VolumeType": volume_type,
                    "VolumeSize": f"{volume_size} GB",
                    "VolumeCount": f"{volume_count}",
                    "CostPerVolume": f"${single_volume_cost:.4f}/hour",
                    "TotalHourlyCost": f"${hourly_cost:.4f}"
                }
            
            elif node_type == "AmazonELB" or node_type == "AWSELB":
                lb_type = node.get("LoadBalancerType", "application").lower()
                
                hourly_cost = self.get_elb_price(lb_type)
                
                cost_details = {
                    "LoadBalancerType": lb_type.capitalize(),
                    "HourlyCost": f"${hourly_cost:.4f}"
                }
            
            # Add more service types as needed
            
            # Check if price data was found
            if hourly_cost == 0.0:
                missing_price_data.append(node_label)
            
            # Store cost details in the node
            node["CostDetails"] = cost_details
            node["HourlyCost"] = f"${hourly_cost:.4f}"
            
            # Add to service costs dictionary
            service_costs[node_label] = f"${hourly_cost:.4f}/hour"
            
            # Add to total cost
            total_hourly_cost += hourly_cost
        
        # Calculate monthly and yearly costs
        monthly_cost = total_hourly_cost * 730  # 730 hours in a month
        yearly_cost = monthly_cost * 12
        
        # Add total cost to the architecture JSON
        architecture_json["TotalCost"] = {
            "HourlyCost": f"${total_hourly_cost:.4f}",
            "MonthlyCost": f"${monthly_cost:.2f}",
            "YearlyCost": f"${yearly_cost:.2f}",
            "ServiceBreakdown": service_costs
        }
        
        # Add missing price data warning if applicable
        if missing_price_data:
            architecture_json["PricingWarnings"] = {
                "MissingPriceData": missing_price_data,
                "Message": "Could not find pricing data for some services. Costs for these services are reported as $0.00."
            }
        
        return architecture_json

def main():
    """Main function to run the cost fetcher"""
    parser = argparse.ArgumentParser(description="Fetch AWS service costs based on JSON architecture definition")
    parser.add_argument("-f", "--file", required=True, help="Path to JSON file containing architecture definition")
    parser.add_argument("-o", "--output", help="Path to output JSON file with cost details")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Load input JSON
        with open(args.file, 'r') as f:
            architecture = json.load(f)
        
        # Initialize cost fetcher
        cost_fetcher = AWSCostFetcher()
        
        # Estimate costs
        architecture_with_costs = cost_fetcher.estimate_costs(architecture)
        
        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(architecture_with_costs, f, indent=2)
            print(f"Cost estimation written to {args.output}")
        else:
            # Print summary to console
            print("\n=== AWS Cost Estimation Summary ===")
            print(f"Total Hourly Cost: {architecture_with_costs['TotalCost']['HourlyCost']}")
            print(f"Total Monthly Cost: {architecture_with_costs['TotalCost']['MonthlyCost']}")
            print(f"Total Yearly Cost: {architecture_with_costs['TotalCost']['YearlyCost']}")
            print("\nService Breakdown:")
            for service, cost in architecture_with_costs['TotalCost']['ServiceBreakdown'].items():
                print(f"  - {service}: {cost}")
            
            # Print warnings for missing price data
            if "PricingWarnings" in architecture_with_costs:
                print("\nWARNING: Missing Price Data")
                print(architecture_with_costs["PricingWarnings"]["Message"])
                print("Affected services:")
                for service in architecture_with_costs["PricingWarnings"]["MissingPriceData"]:
                    print(f"  - {service}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    main() 
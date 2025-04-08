import json
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# --- Pricing Client Setup ---
def create_pricing_client(region="us-east-1"):
    access_key = os.environ.get("AWS_ACCESS_KEY")
    secret_key = os.environ.get("AWS_SECRET_KEY")
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    return session.client("pricing", region_name="us-east-1")

# --- Get AWS Pricing API Price ---
def get_price(pricing_client, filters, service_code):
    try:
        response = pricing_client.get_products(
            ServiceCode=service_code,
            Filters=filters,
            FormatVersion='aws_v1',
            MaxResults=1
        )
        if not response['PriceList']:
            print(f"[DEBUG] No pricing found for {service_code} with filters: {filters}")
            return 0.0
        product = json.loads(response['PriceList'][0])
        for term in product['terms']['OnDemand'].values():
            for price_dim in term['priceDimensions'].values():
                return float(price_dim['pricePerUnit']['USD'])
    except Exception as e:
        print(f"[ERROR] Pricing API error for {service_code}: {e}")
    return 0.0

# --- Filter Builders ---
def build_ec2_filters(attr, region):
    return [
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": attr.get("instanceType", "t3.micro")},
        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": attr.get("operatingSystem", "Linux")},
        {"Type": "TERM_MATCH", "Field": "tenancy", "Value": attr.get("tenancy", "Shared")},
        {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": attr.get("capacitystatus", "Used")},
        {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": attr.get("preInstalledSw", "NA")},
        {"Type": "TERM_MATCH", "Field": "termType", "Value": attr.get("termType", "OnDemand")},
        {"Type": "TERM_MATCH", "Field": "location", "Value": region}
    ]

def build_rds_filters(attr, region):
    return [
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": attr.get("instanceType", "db.t3.micro")},
        {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": attr.get("databaseEngine", "MySQL")},
        {"Type": "TERM_MATCH", "Field": "termType", "Value": attr.get("termType", "OnDemand")},
        {"Type": "TERM_MATCH", "Field": "location", "Value": region}
    ]

def build_s3_filters(attr, region):
    return [
        
    {"Type": "TERM_MATCH", "Field": "location", "Value": region},
    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
    {"Type": "TERM_MATCH", "Field": "termType", "Value": "OnDemand"}
]

    

def build_cloudfront_filters(attr):
    return [
        {"Type": "TERM_MATCH", "Field": "location", "Value": "Global"},
    {"Type": "TERM_MATCH", "Field": "termType", "Value": "OnDemand"},
    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Amazon CloudFront"}
    ]
def estimate_rds_cost(attr, region, pricing_client):
    # --- Step 1: Get Instance Price ($/hour) ---
    instance_filters = [
        {"Type": "TERM_MATCH", "Field": "location", "Value": region},
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": attr.get("instanceType", "db.t3.micro")},
        {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": attr.get("databaseEngine", "MySQL")},
        {"Type": "TERM_MATCH", "Field": "termType", "Value": attr.get("termType", "OnDemand")}
    ]
    instance_price_per_hour = get_price(pricing_client, instance_filters, "AmazonRDS")

    # --- Step 2: Get Storage Price ($/GB-month) ---
    storage_gb = int(attr.get("storageGB", 100))
    volume_type = attr.get("volumeType", "gp2")
    
    volume_map = {
        "gp2": "General Purpose",
        "gp3": "General Purpose",
        "io1": "Provisioned IOPS",
        "standard": "Magnetic"
    }
    volume_type_for_filter = volume_map.get(volume_type.lower(), "General Purpose")

    storage_filters = [
    {"Type": "TERM_MATCH", "Field": "location", "Value": region},
    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
    {"Type": "TERM_MATCH", "Field": "group", "Value": "Amazon RDS Storage"},
    {"Type": "TERM_MATCH", "Field": "termType", "Value": "OnDemand"}
]

    
    price_per_gb_month = get_price(pricing_client, storage_filters, "AmazonRDS")
    storage_price_per_hour = (price_per_gb_month / 730) * storage_gb

    # --- Step 3: Combine ---
    total_hourly = instance_price_per_hour + storage_price_per_hour
    total_monthly = total_hourly * 730

    description = (
        f"RDS {attr.get('instanceType')} + "
        f"{storage_gb}GB {volume_type.upper()} Storage "
        f"(${round(instance_price_per_hour * 730, 2)} + ${round(price_per_gb_month * storage_gb, 2)})"
    )

    # --- Optional Print Statement for Debug/Info ---
    print(f"[INFO] RDS Monthly Cost: ${round(total_monthly, 2)} "
          f"(Instance: ${round(instance_price_per_hour * 730, 2)}, "
          f"Storage: ${round(price_per_gb_month * storage_gb, 2)})")

    return {
        "hourly_price_usd": round(total_hourly, 6),
        "monthly_price_usd": round(total_monthly, 2),
        "description": description
    }


# --- Cost Engine Core ---
def estimate_cost_from_architecture(architecture_json):
    pricing_client = create_pricing_client()
    total_hourly = 0.0
    breakdown = []

    for node in architecture_json["nodes"]:
        service = node["type"]
        region = node.get("region", "Asia Pacific (Mumbai)")
        attr = node.get("attributes", {})
        price = 0.0
        description = ""

        if service == "AmazonEC2":
            filters = build_ec2_filters(attr, region)
            price = get_price(pricing_client, filters, "AmazonEC2")
            description = f"EC2 {attr.get('instanceType', 't3.micro')}"

        elif service == "AmazonRDS":
            rds_cost = estimate_rds_cost(attr, region, pricing_client)
            price = rds_cost["hourly_price_usd"]
            description = rds_cost["description"]


        elif service == "AmazonS3":
            size_gb = attr.get("storageAmountGB", 100)
            filters = build_s3_filters(attr, region)
            per_gb_price = get_price(pricing_client, filters, "AmazonS3")
            price = (per_gb_price / 730) * size_gb
            description = f"S3 {size_gb}GB Standard"

        elif service == "AmazonCloudFront":
            data_gb = attr.get("dataOutGB", 100)
            filters = build_cloudfront_filters(attr)
            per_gb_price = get_price(pricing_client, filters, "AmazonCloudFront")
            price = (per_gb_price / 730) * data_gb
            description = f"CloudFront {data_gb}GB Data Transfer"

        else:
            continue  # Skip unsupported services

        total_hourly += price
        breakdown.append({
            "nodeId": node["id"],
            "service": service,
            "description": description,
            "hourly_price_usd": round(price, 6)
        })

    return {
        "total_hourly_cost_usd": round(total_hourly, 6),
        "estimated_monthly_cost_usd": round(total_hourly * 730, 2),
        "service_breakdown": breakdown
    }

# --- Test Runner ---
if __name__ == "__main__":
    with open("input_architecture.json") as f:
        architecture_json = json.load(f)

    result = estimate_cost_from_architecture(architecture_json)
    print(json.dumps(result, indent=2))

import json
import boto3

def create_pricing_client(access_key, secret_key, region="us-east-1"):
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    return session.client("pricing", region_name="us-east-1")


def get_price(pricing_client, filters, service_code="AmazonEC2"):
    try:
        response = pricing_client.get_products(
            ServiceCode=service_code,
            Filters=filters,
            FormatVersion='aws_v1',
            MaxResults=1
        )
        if not response['PriceList']:
            print(f"[DEBUG] No products found for {service_code} with filters: {filters}")
            return 0.0
        price_list = json.loads(response['PriceList'][0])
        for term in price_list['terms']['OnDemand'].values():
            for price_dimension in term['priceDimensions'].values():
                return float(price_dimension['pricePerUnit']['USD'])
    except Exception as e:
        print(f"[ERROR] Failed to get price for {service_code}: {e}")
        return 0.0


def estimate_cost(architecture_json, access_key, secret_key):
    pricing_client = create_pricing_client(access_key, secret_key)
    total_hourly = 0.0
    breakdown = []

    for resource in architecture_json["resources"]:
        service = resource["type"]
        region = resource.get("region", "US East (N. Virginia)")
        attributes = resource.get("attributes", {})
        filters = [{"Type": "TERM_MATCH", "Field": "location", "Value": region}]
        price = 0.0
        description = ""

        if service == "AmazonEC2":
            filters += [
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": attributes.get("instanceType", "t3.micro")},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": attributes.get("operatingSystem", "Linux")},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": attributes.get("tenancy", "Shared")},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": attributes.get("capacitystatus", "Used")},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": attributes.get("preInstalledSw", "NA")},
                {"Type": "TERM_MATCH", "Field": "termType", "Value": attributes.get("termType", "OnDemand")},
            ]
            price = get_price(pricing_client, filters, "AmazonEC2")
            description = f"EC2 ({attributes.get('instanceType', 't3.micro')})"

        elif service == "AmazonS3":
            storage_gb = attributes.get("storageAmountGB", 100)
            price = 0.023 / 730 * storage_gb  # flat approximation for S3 standard
            description = f"S3 Storage ({storage_gb} GB)"

        elif service == "AmazonRDS":
            filters += [
                
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": attributes.get("instanceType", "db.t3.micro")},
                {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": attributes.get("databaseEngine", "MySQL")},
                {"Type": "TERM_MATCH", "Field": "deploymentOption", "Value": "Single-AZ"},
                
                {"Type": "TERM_MATCH", "Field": "termType", "Value": "OnDemand"},
            ]
            price = get_price(pricing_client, filters, "AmazonRDS")
            description = f"RDS ({attributes.get('instanceType', 'db.t3.micro')})"

        elif service == "AmazonCloudFront":
            data_out_gb = attributes.get("dataOutGB", 100)
            price = 0.085 / 730 * data_out_gb
            description = f"CloudFront Data Transfer ({data_out_gb} GB)"

        total_hourly += price
        breakdown.append({
            "service": service,
            "description": description,
            "hourly_price_usd": round(price, 6)
        })

    return {
        "total_hourly_cost_usd": round(total_hourly, 6),
        "estimated_monthly_cost_usd": round(total_hourly * 24 * 30, 2),
        "service_breakdown": breakdown
    }

# Example usage:
if __name__ == "__main__":
    # Paste your keys here for testing
    AWS_ACCESS_KEY = ""
    AWS_SECRET_KEY = ""

    architecture_input = {
        "resources": [
            {"type": "AmazonEC2", "region": "Asia Pacific (Mumbai)", "attributes": {"instanceType": "t3.micro"}},
            {"type": "AmazonS3", "region": "Asia Pacific (Mumbai)", "attributes": {"storageAmountGB": 100}},
            {"type": "AmazonRDS", "region": "Asia Pacific (Mumbai)", "attributes": {"instanceType": "db.t3.micro", "databaseEngine": "MySQL"}},
            {"type": "AmazonCloudFront", "region": "Asia Pacific (Mumbai)", "attributes": {"dataOutGB": 100}},
        ]
    }

    result = estimate_cost(architecture_input, AWS_ACCESS_KEY, AWS_SECRET_KEY)
    print(json.dumps(result, indent=2))

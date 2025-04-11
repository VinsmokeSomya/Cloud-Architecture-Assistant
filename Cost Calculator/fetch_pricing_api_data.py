import requests
import json

PRICING_API = 'https://pricing.us-east-1.amazonaws.com'  # AWS Pricing API base URL
OFFER_INDEX = '/offers/v1.0/aws/index.json'  # Path to AWS service offerings index

def fetch_pricing_data():
    try:
        # Fetch the AWS Pricing API data
        response = requests.get(PRICING_API + OFFER_INDEX)
        response.raise_for_status()  # Raise an error for HTTP issues
        data = response.json()  # Parse the JSON response

        # Save the data to a file for inspection
        with open("pricing_api_data.json", "w") as file:
            json.dump(data, file, indent=4)

        # Print the keys and structure of the data
        print("Top-level keys in the API response:")
        for key in data.keys():
            print(f"- {key}")

        print("\nExample of 'offers' key structure:")
        offers = data.get("offers", {})
        for offer_key, offer_value in list(offers.items())[:5]:  # Print first 5 offers
            print(f"\nOffer Key: {offer_key}")
            print(f"Offer Details: {json.dumps(offer_value, indent=4)}")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from AWS Pricing API: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")

if __name__ == "__main__":
    fetch_pricing_data()
    
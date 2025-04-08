from __future__ import print_function, unicode_literals  # Enable Python 3 print function and unicode literals

import botocore.session  # Import AWS SDK session management
import inquirer  # Import interactive command line interface library
import pandas as pd  # Import pandas for data manipulation
import requests  # Import requests for HTTP calls
from yaspin import yaspin  # Import spinner for loading animations

session = botocore.session.get_session()  # Create AWS session
regions = session.get_available_regions('ec2')  # Get list of available AWS regions

PRICING_API='https://pricing.us-east-1.amazonaws.com'  # AWS Pricing API base URL
OFFER_INDEX='/offers/v1.0/aws/index.json'  # Path to AWS service offerings index
DONE_ITEM = '✓ done'  # Symbol for completing selection
SPINNER_OK = '✅ '  # Symbol for successful operation
SPINNER_FAIL = '💥 '  # Symbol for failed operation

def load_offers():
    with yaspin(text='Querying ' + PRICING_API + OFFER_INDEX, color="yellow") as spinner:  # Show loading spinner
        try:
            index_response = requests.get(PRICING_API + OFFER_INDEX)  # Fetch AWS service offerings
            spinner.ok(SPINNER_OK)  # Show success symbol
            return index_response.json()['offers']  # Return available service offerings
        except:
            spinner.fail(SPINNER_FAIL)  # Show failure symbol
            return None

def prompt_region():
    question = [  # Create region selection prompt
        inquirer.List('region',
                  message="Select and AWS Region?",  # Prompt message
                  choices=regions,  # Available regions
                  default='eu-central-1',  # Default selection
                  carousel=True,  # Enable scrolling
              )
    ]

    answer = inquirer.prompt(question)  # Show prompt and get user input
    return answer['region'] if answer else None  # Return selected region or None

def prompt_service(services_list, service):
    question = [  # Create service selection prompt
        inquirer.List('service',
                  message="Select and AWS Service?",  # Prompt message
                  choices=services_list,  # Available services
                  default=service,  # Default selection
                  carousel=True,  # Enable scrolling
              )
    ]

    answer = inquirer.prompt(question)  # Show prompt and get user input
    return answer['service'] if answer else None  # Return selected service or None

def get_regional_service(region, offer):
    regional_service_offer = requests.get(PRICING_API + offer['currentRegionIndexUrl'])  # Fetch regional service data
    offer_regions = regional_service_offer.json()['regions']  # Get available regions for service
    offer_region = offer_regions.get(region, {})  # Get specific region data
    current_version_url = offer_region.get('currentVersionUrl', None)  # Get current pricing version URL

    if current_version_url:  # If pricing data exists for region
        with yaspin(text='Querying ' + PRICING_API + current_version_url, color="yellow") as spinner:  # Show loading spinner
            service_pricing = requests.get(PRICING_API + current_version_url)  # Fetch pricing data
            spinner.ok(SPINNER_OK)  # Show success symbol
            return service_pricing.json()  # Return pricing data

def get_options_list(options_list, service_offer):
    return_options = []  # Initialize list for options

    for product in options_list:  # Iterate through products
        for offer in options_list[product]:  # Iterate through offers
            for price in options_list[product][offer]['priceDimensions']:  # Iterate through price dimensions
                item = options_list.get(product, {}).get(offer, {}).get('priceDimensions', {}).get(price, {})  # Get price details
                if item:  # If price details exist
                    item_id = item['rateCode'].split('.')  # Split rate code

                    product_offer = service_offer['products'][item_id[0]]  # Get product details

                    return_options.append({  # Add option to list
                        'name': item['description'],  # Option name
                        'key': item['rateCode'],  # Unique identifier
                        'unit': item['unit'],  # Pricing unit
                        'price': item['pricePerUnit']['USD'],  # Price in USD
                        'productFamily': product_offer.get('productFamily', 'Other'),  # Product family
                        'attributes': product_offer.get('attributes', {}),  # Product attributes
                    })

    return return_options  # Return list of options

def get_product_label(x):
    if x['attributes'] and x['attributes']['servicecode'] == 'AmazonEC2':  # If EC2 instance
        return f"{x['attributes']['instanceFamily']} - {x['attributes']['instanceType']} - {x['attributes']['operatingSystem']} - vcpu={x['attributes']['vcpu']} - {x['attributes']['tenancy']} - {x['attributes']['preInstalledSw']} - {x['attributes']['capacitystatus']}"  # Format EC2 label
    else:
        return x['name']  # Return simple name for other services

def prompt_service_form(service_offer, service):
    terms = service_offer.get('terms', {})  # Get pricing terms
    products = service_offer.get('products', {})  # Get product details

    ondemand_options = get_options_list(terms.get('OnDemand', {}), service_offer)  # Get on-demand options
    reserved_options = get_options_list(terms.get('Reserved', {}), service_offer)  # Get reserved options

    style_options = [  # Create pricing model options
        'OnDemand' if len(ondemand_options) > 1 else None,  # Add on-demand if available
        'Reserved'  if len(reserved_options) > 1 else None,  # Add reserved if available
        DONE_ITEM,  # Add done option
    ]

    styles = [  # Create pricing model selection prompt
        inquirer.List('style',
            message='Select the pricing model',  # Prompt message
            choices=[s for s in style_options if s is not None],  # Available options
            carousel=True,  # Enable scrolling
        )
    ]

    calculations = []  # Initialize calculations list
    while True:  # Loop until done
        selected_style = inquirer.prompt(styles)  # Get pricing model selection

        if selected_style and selected_style['style'] == 'OnDemand':  # If on-demand selected
            choices = ondemand_options  # Use on-demand options
        elif selected_style and selected_style['style'] == 'Reserved':  # If reserved selected
            choices = reserved_options  # Use reserved options
        else:
            return calculations  # Return calculations if done

        prod_families = sorted(set([x.get('productFamily') for x in choices if x.get('productFamily') is not None]))  # Get product families
        prod_families.append(('<- back', '<- back'))  # Add back option

        family_options = [  # Create product family selection prompt
            inquirer.List('family',
                message='Select the product family',  # Prompt message
                choices=prod_families,  # Available families
                carousel=True,  # Enable scrolling
            ),
        ]

        choosen_family = inquirer.prompt(family_options)  # Get family selection
        if choosen_family and choosen_family['family'] != '<- back':  # If family selected
            type_choices = list(filter(lambda x: x.get('productFamily') == choosen_family['family'], choices))  # Filter by family
            selected_type_choices = sorted([(get_product_label(x), x['key']) for x in type_choices])  # Format choices
            selected_type_choices.append(('<- back', '<- back'))  # Add back option

            pricing_options = [  # Create product selection prompt
                inquirer.List('type',
                    message='Select the product',  # Prompt message
                    choices=selected_type_choices,  # Available products
                    carousel=True,  # Enable scrolling
                ),
            ]
            
            print(pricing_options)  # Show pricing options

            choosen_pricing = inquirer.prompt(pricing_options)  # Get product selection

            if choosen_pricing and choosen_pricing['type'] != '<- back':  # If product selected
                choosen_items = list(filter(lambda x: x['key'] == choosen_pricing['type'], choices))  # Get selected item
                choosen_item = choosen_items[0] if choosen_items else None  # Get first matching item
                if choosen_item:  # If item found
                    questions = [  # Create quantity prompt
                        inquirer.Text('value', message=f'{choosen_item["productFamily"]} - How many {choosen_item["unit"]}?'),  # Prompt message
                    ]

                    answers = inquirer.prompt(questions)  # Get quantity
                    if answers and answers['value']:  # If quantity provided
                        calculations.append({  # Add calculation to list
                            'name': choosen_pricing['type'],  # Product name
                            'service': service,  # Service name
                            'type': selected_style['style'],  # Pricing type
                            'family': choosen_family['family'],  # Product family
                            'value': float(answers['value']) * float(choosen_item['price']),  # Calculate cost
                        })

def print_summary(total_expenses):
    flatten_items = [item for items in total_expenses for item in items]  # Flatten nested list
    if flatten_items:  # If items exist
        df = pd.DataFrame(data=flatten_items)  # Create DataFrame
        print(df.groupby(["service", "type"]).sum())  # Print summary by service and type
        print("---------------------------------------")  # Print separator
        print("Grand Total: USD", format(df["value"].sum(), 'f'))  # Print total cost

def execute_routine(offers):
    services = sorted([x for x in offers])  # Get sorted list of services
    service = None  # Initialize service
    region = prompt_region()  # Get region selection
    if region:  # If region selected
        services.append(DONE_ITEM)  # Add done option
        total_expenses = []  # Initialize expenses list
        while True:  # Loop until done
            service = prompt_service(services, service)  # Get service selection
            if (service and service != DONE_ITEM):  # If service selected
                offer = offers[service]  # Get service offer
                service_offer = get_regional_service(region, offer)  # Get regional pricing
                if (service_offer):  # If pricing available
                    total_expenses.append(prompt_service_form(service_offer, service))  # Get service calculations
            else:
                break  # Exit loop if done

        print_summary(total_expenses)  # Print cost summary

offers = load_offers()  # Load AWS service offerings
if offers:  # If offerings loaded
    execute_routine(offers)  # Start cost estimation
else:
    print("Could not fetch offers!")  # Show error message
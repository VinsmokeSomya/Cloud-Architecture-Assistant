from __future__ import print_function, unicode_literals  # Enable Python 3 print function and unicode literals
import botocore.session  # Import AWS SDK session management
import inquirer  # Import interactive command line interface library
import pandas as pd  # Import pandas for data manipulation
import requests  # Import requests for HTTP calls
from yaspin import yaspin  # Import spinner for loading animations
import streamlit as st  # Import streamlit for Streamlit app
import json # Import json for pretty printing attributes

session = botocore.session.get_session()  # Create AWS session
regions = session.get_available_regions('ec2')  # Get list of available AWS regions

PRICING_API='https://pricing.us-east-1.amazonaws.com'  # AWS Pricing API base URL
OFFER_INDEX='/offers/v1.0/aws/index.json'  # Path to AWS service offerings index
DONE_ITEM = '✓ done'  # Symbol for completing selection
SPINNER_OK = '✅ '  # Symbol for successful operation
SPINNER_FAIL = '💥 '  # Symbol for failed operation
DEFAULT_REGION = 'ap-south-1' # Default region to pre-select

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
                  default='ap-south-1',  # Default selection
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

def get_options_list(options_dict, service_offer_products):
    """Extracts and formats pricing options from the terms dictionary."""
    return_options = []
    if not isinstance(options_dict, dict):
        return [] # Return empty list if input is not a dictionary

    for product_sku, product_offers in options_dict.items():
        if not isinstance(product_offers, dict): continue
        for offer_term_code, offer_details in product_offers.items():
            if not isinstance(offer_details, dict): continue
            price_dimensions = offer_details.get('priceDimensions')
            if not isinstance(price_dimensions, dict): continue

            for price_dimension_key, price_info in price_dimensions.items():
                if not isinstance(price_info, dict): continue
                product_details = service_offer_products.get(product_sku, {})
                attributes = product_details.get('attributes', {})
                product_family = product_details.get('productFamily', 'Unknown Family')

                return_options.append({
                    'name': price_info.get('description', 'No description'),
                    'key': price_info.get('rateCode', f"{product_sku}.{offer_term_code}.{price_dimension_key}"), # Fallback key
                    'unit': price_info.get('unit', 'Unknown Unit'),
                    'price': float(price_info.get('pricePerUnit', {}).get('USD', 0.0)),
                    'productFamily': product_family,
                    'attributes': attributes,
                    'sku': product_sku, # Keep sku for reference
                })
    return return_options

def get_product_label(item_details):
    """Creates a descriptive label for a product based on its attributes."""
    if not isinstance(item_details, dict): return "Invalid Item"

    attributes = item_details.get('attributes', {})
    product_family = item_details.get('productFamily', 'Unknown')
    name = item_details.get('name', 'Unknown Name') # Use description as base name

    # --- Custom Labels for Common Services ---
    if 'instanceType' in attributes: # Likely EC2, RDS, ElastiCache, etc.
        label = f"{attributes.get('instanceType')}"
        if 'vcpu' in attributes: label += f" ({attributes['vcpu']} vCPU"
        if 'memory' in attributes: label += f", {attributes['memory']}"
        if 'vcpu' in attributes or 'memory' in attributes: label += ")" # Close parenthesis if details added
        if 'operatingSystem' in attributes: label += f" - {attributes['operatingSystem']}"
        if 'databaseEngine' in attributes: label += f" - {attributes['databaseEngine']}"
        if 'deploymentOption' in attributes: label += f" ({attributes['deploymentOption']})"
        return f"{product_family}: {label}"

    if 'volumeType' in attributes: # Likely EBS, EFS
        return f"{product_family}: {attributes.get('volumeType', name)}"

    if 'messageDeliveryFrequency' in attributes: # Likely SQS
         return f"{product_family}: {attributes.get('messageDeliveryFrequency', name)}"

    if 'group' in attributes: # Can be ELB, Lambda, etc.
        return f"{product_family} ({attributes.get('group')}): {name}"

    # --- Generic Fallback ---
    return f"{product_family}: {name}"

def prompt_service_form(service_offer, service):
    terms = service_offer.get('terms', {})  # Get pricing terms
    products = service_offer.get('products', {})  # Get product details

    ondemand_options = get_options_list(terms.get('OnDemand', {}), products)  # Get on-demand options
    reserved_options = get_options_list(terms.get('Reserved', {}), products)  # Get reserved options

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

# --- Streamlit App ---

@st.cache_data(ttl=3600) # Cache for 1 hour
def load_offers_cached():
    # Use yaspin context manager if needed, or just print status
    print("Executing load_offers...")
    with yaspin(text='Querying AWS Offer Index...', color="yellow") as spinner:
        try:
            offers_data = load_offers() # Call your original load_offers
            if offers_data:
                spinner.ok(SPINNER_OK)
                print("Finished load_offers.")
                return offers_data
            else:
                spinner.fail(SPINNER_FAIL)
                print("Failed load_offers.")
                return None
        except Exception as e:
            spinner.fail(SPINNER_FAIL)
            print(f"Error in load_offers: {e}")
            return None

@st.cache_data(ttl=3600) # Cache for 1 hour
def get_regional_service_cached(region, current_region_index_url):
     print(f"Executing get_regional_service for {region}...")
     # Need to fetch the regional service data based on the URL
     try:
         with yaspin(text=f'Querying regional data for {region}...', color="yellow") as spinner:
             regional_service_offer = requests.get(PRICING_API + current_region_index_url)
             regional_service_offer.raise_for_status() # Raise error for bad status codes
             offer_regions = regional_service_offer.json()['regions']
             offer_region = offer_regions.get(region, {})
             current_version_url = offer_region.get('currentVersionUrl', None)

             if current_version_url:
                 service_pricing_req = requests.get(PRICING_API + current_version_url)
                 service_pricing_req.raise_for_status()
                 service_pricing_data = service_pricing_req.json()
                 spinner.ok(SPINNER_OK)
                 print(f"Finished get_regional_service for {region}.")
                 return service_pricing_data
             else:
                 spinner.text = f"No regional service URL found for {region}."
                 spinner.ok("ℹ️ ") # Use info symbol
                 print(f"No regional service URL found for {region}.")
                 return None
     except requests.exceptions.RequestException as e:
         print(f"HTTP Error fetching regional service for {region}: {e}")
         # spinner might not exist here if the first request failed, handle gracefully
         # Consider adding spinner.fail here if possible
         return None
     except Exception as e:
        print(f"Error in get_regional_service_cached for {region}: {e}")
        # spinner might not exist here, handle gracefully
        return None

def display_summary(calculations_list):
    """Displays the cost summary in Streamlit."""
    if not calculations_list:
        st.info("Add items to the calculation to see a summary.")
        return

    st.markdown("---")
    st.subheader("💰 Final Cost Summary")
    df = pd.DataFrame(data=calculations_list)

    # Display detailed breakdown
    st.dataframe(
        df[[
            'service', 'region', 'type', 'family', 'name',
            'quantity', 'unit', 'unit_price', 'value'
         ]].round({'unit_price': 6, 'value': 2}), # More precision for unit price
         hide_index=True # Cleaner look
    )

    # Display aggregated summary
    st.subheader("Summary by Service and Type")
    # Group by region as well
    summary_df = df.groupby(["service", "region", "type"])['value'].sum().reset_index()
    st.dataframe(summary_df.round(2), hide_index=True)

    grand_total = df["value"].sum()
    st.metric("Grand Total (USD)", f"${grand_total:,.2f}")

def main_st():
    st.set_page_config(layout="wide", page_title="AWS Cost Calculator")
    st.title("☁️ AWS Cost Calculator")
    st.caption("Estimate costs using the AWS Pricing API.")

    # --- Initialize Session State ---
    if 'calculations' not in st.session_state:
        st.session_state.calculations = []
    if 'selected_region' not in st.session_state:
        st.session_state.selected_region = DEFAULT_REGION
    if 'selected_service' not in st.session_state:
        st.session_state.selected_service = None
    # Add keys for cascading select boxes if needed, though Streamlit often handles this well

    # --- Load AWS Offers ---
    # Use st.spinner for loading feedback in Streamlit
    with st.spinner("Loading AWS Service Offers..."):
        offers = load_offers_cached()

    if not offers:
        st.error("Could not load AWS service offers. Please check network connection or refresh.")
        st.stop() # Stop execution if offers can't be loaded

    # --- Main Area for Selections ---

    # --- 1. Region Selection (Moved to Main Area) ---
    aws_session = botocore.session.get_session()
    try:
        # Use a common service like 'ec2' which is available in most regions
        available_regions = aws_session.get_available_regions('ec2')
    except Exception as e:
        st.error(f"Could not fetch regions: {e}")
        available_regions = [DEFAULT_REGION] # Fallback

    # Ensure default region is valid, otherwise use the first available
    if st.session_state.selected_region not in available_regions:
        st.session_state.selected_region = available_regions[0] if available_regions else None

    if st.session_state.selected_region:
        st.session_state.selected_region = st.selectbox( # Changed from st.sidebar.selectbox
            "Select AWS Region",
            available_regions,
            index=available_regions.index(st.session_state.selected_region),
            key='region_select_main' # Use a different key if needed
        )
        # Display selected region below the dropdown
        st.write(f"Selected Region: **{st.session_state.selected_region}**")
    else:
        st.warning("No AWS regions available.")
        st.stop()

    # --- 2. Service Selection (Moved to Main Area) ---
    services_list = sorted(offers.keys())
    st.session_state.selected_service = st.selectbox( # Changed from st.sidebar.selectbox
        "Select AWS Service to Add",
        [""] + services_list, # Add empty option to allow deselection
        index= (services_list.index(st.session_state.selected_service) + 1) if st.session_state.selected_service in services_list else 0,
        key='service_select_main' # Use a different key if needed
    )

    st.markdown("---") # Add a separator

    # --- Main Area for Configuration & Calculation ---
    if st.session_state.selected_service:
        selected_service_key = st.session_state.selected_service
        st.header(f"Configure: {selected_service_key}")
        offer = offers[selected_service_key]
        region_index_url = offer.get('currentRegionIndexUrl')

        if not region_index_url:
            st.warning(f"Offer data for **{selected_service_key}** does not contain a regional index URL. Pricing might be global or unavailable via this method.")
        else:
            # --- Fetch Regional Service Offer ---
            with st.spinner(f"Loading pricing for {selected_service_key} in {st.session_state.selected_region}..."):
                service_offer = get_regional_service_cached(st.session_state.selected_region, region_index_url)

            if not service_offer:
                st.warning(f"No pricing information found for **{selected_service_key}** in **{st.session_state.selected_region}**. The service might not be available, might not have published pricing data in this region, or there was an error fetching the data.")
            else:
                # --- Extract Pricing Options ---
                terms = service_offer.get('terms', {})
                service_offer_products = service_offer.get('products', {}) # Needed for attributes

                # Check if products data exists
                if not service_offer_products:
                     st.warning(f"No product details found for **{selected_service_key}** in **{st.session_state.selected_region}** in the fetched data.")
                     # Allow proceeding if terms exist, but labeling might be basic
                     # st.stop() # Option: Stop if no product details

                ondemand_options = get_options_list(terms.get('OnDemand', {}), service_offer_products)
                reserved_options = get_options_list(terms.get('Reserved', {}), service_offer_products)

                style_options_dict = {}
                if ondemand_options: style_options_dict["OnDemand"] = ondemand_options
                if reserved_options: style_options_dict["Reserved"] = reserved_options

                if not style_options_dict:
                    st.info(f"No configurable OnDemand or Reserved pricing options found for **{selected_service_key}** in **{st.session_state.selected_region}** via the Pricing API.")
                else:
                    # --- 3. Pricing Model Selection ---
                    # Use a unique key to help Streamlit manage state correctly when service/region changes
                    style_radio_key = f'style_radio_{selected_service_key}_{st.session_state.selected_region}'
                    selected_style = st.radio(
                        "Select Pricing Model", # Updated label
                        list(style_options_dict.keys()),
                        key=style_radio_key,
                        horizontal=True
                    )

                    if selected_style:
                        current_options = style_options_dict[selected_style]
                        product_families = sorted(list(set(opt['productFamily'] for opt in current_options if opt.get('productFamily'))))

                        if not product_families:
                             st.info("No product families found for the selected pricing model.")
                        else:
                            # --- 4. Product Family Selection ---
                            family_select_key = f'family_select_{selected_service_key}_{selected_style}_{st.session_state.selected_region}'
                            selected_family = st.selectbox(
                                "Select Product Family", # Updated label
                                [""] + product_families, # Add empty option
                                key=family_select_key
                            )

                            if selected_family:
                                # Filter options by selected family
                                family_options = [opt for opt in current_options if opt.get('productFamily') == selected_family]
                                # Create labels and map to keys for selectbox
                                type_labels_keys = sorted([(get_product_label(opt), opt['key']) for opt in family_options])

                                # Check for duplicate labels (can happen with complex pricing)
                                labels = [label for label, key in type_labels_keys]
                                if len(labels) != len(set(labels)):
                                    st.warning("Duplicate product labels detected. Using internal keys for selection.")
                                    # Use RateCode (key) directly if labels are ambiguous
                                    type_display_options = {key: f"{get_product_label(opt)} ({key})" for opt in family_options for label, k in type_labels_keys if k == opt['key']}
                                else:
                                    type_display_options = {key: label for label, key in type_labels_keys}

                                available_keys = [""] + list(type_display_options.keys()) # Add empty option first

                                # --- 5. Product Selection ---
                                type_select_key = f'type_select_{selected_service_key}_{selected_style}_{selected_family}_{st.session_state.selected_region}'
                                selected_type_key = st.selectbox(
                                    "Select Specific Product/Type",
                                    options=available_keys,
                                    format_func=lambda key: type_display_options.get(key, "--- Select ---"), # Show label
                                    key=type_select_key
                                )

                                if selected_type_key:
                                    # Find the full details of the chosen item
                                    chosen_item = next((opt for opt in family_options if opt['key'] == selected_type_key), None)

                                    if chosen_item:
                                        st.markdown("---")
                                        col1, col2 = st.columns([2,1])
                                        with col1:
                                            st.write(f"**Selected Item:**")
                                            # Use markdown for better formatting control
                                            st.markdown(f"**Description:** `{chosen_item.get('name', 'N/A')}`")
                                            st.markdown(f"**Pricing Unit:** `{chosen_item.get('unit', 'N/A')}`")
                                            st.markdown(f"**Price/Unit (USD):** `{chosen_item.get('price', 0.0):.6f}`") # Show more precision

                                            # Show attributes if they exist
                                            attributes = chosen_item.get('attributes')
                                            if attributes and isinstance(attributes, dict):
                                                 with st.expander("View Attributes"):
                                                      # Use json.dumps for potentially cleaner display than st.json for nested dicts
                                                      st.code(json.dumps(attributes, indent=2), language='json')

                                        with col2:
                                            # --- 6. Quantity Input ---
                                            quantity_input_key = f'quantity_input_{selected_type_key}' # Unique key
                                            # Determine a sensible step based on unit
                                            unit = chosen_item.get("unit", "").lower()
                                            step = 1.0
                                            if 'request' in unit or 'gb-mo' in unit or 'gb-month' in unit:
                                                step = 1.0
                                            elif 'hour' in unit:
                                                step = 1.0
                                            elif 'gb' in unit and 'hour' not in unit:
                                                 step = 1.0 # Or maybe 10? Depends on context
                                            # Add more specific steps if needed

                                            quantity = st.number_input(
                                                f'Enter Quantity ({chosen_item.get("unit", "Units")})', # Updated label
                                                min_value=0.0,
                                                value=1.0,
                                                step=step,
                                                key=quantity_input_key
                                            )

                                            # --- 7. Add Button ---
                                            add_button_key = f'add_button_{selected_type_key}'
                                            if st.button(f"Add to Calculation", key=add_button_key, type="primary", use_container_width=True):
                                                if quantity > 0:
                                                    cost = float(quantity) * float(chosen_item.get('price', 0.0))
                                                    # Create a unique ID for each added item for potential removal
                                                    item_id = f"{selected_type_key}_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}"
                                                    calc_item = {
                                                        'id': item_id, # Unique ID for removal
                                                        'service': selected_service_key,
                                                        'region': st.session_state.selected_region,
                                                        'type': selected_style,
                                                        'family': selected_family,
                                                        'name': get_product_label(chosen_item), # Use the generated label
                                                        'unit': chosen_item.get('unit', 'N/A'),
                                                        'quantity': quantity,
                                                        'unit_price': float(chosen_item.get('price', 0.0)),
                                                        'value': cost,
                                                        'key': chosen_item['key'] # Original rate code
                                                    }
                                                    st.session_state.calculations.append(calc_item)
                                                    st.success(f"Added: {quantity} {chosen_item.get('unit')} of {get_product_label(chosen_item)}")
                                                    # No rerun needed, Streamlit updates automatically usually
                                                    # st.rerun() # Force rerun if state updates aren't reflected quickly
                                                else:
                                                    st.warning("Quantity must be greater than 0.")
    else:
        # Keep this section, maybe adjust spacing if needed
        st.info("Select a region and service above to begin configuration.") # Updated message


    # --- Display Current Calculations Table & Removal ---
    st.markdown("---")
    st.header("📊 Current Calculation Items")

    if st.session_state.calculations:
        calc_df = pd.DataFrame(st.session_state.calculations)

        # Use st.data_editor for interactive editing/removal (newer Streamlit feature)
        # Or build the table manually with remove buttons
        st.write("Calculation Details:")
        # Make a copy for display formatting
        display_df_data = calc_df[[
             'service', 'region', 'type', 'family', 'name',
             'quantity', 'unit', 'unit_price', 'value', 'id' # Keep id for removal logic
         ]].copy()
        display_df_data['unit_price'] = display_df_data['unit_price'].map('{:.6f}'.format)
        display_df_data['value'] = display_df_data['value'].map('{:.2f}'.format)

        # Define column configuration for data_editor if using that
        # column_config = { ... }

        # --- Manual Table with Remove Buttons ---
        # Define columns dynamically based on the dataframe, plus one for 'Action'
        column_names = list(display_df_data.columns[:-1]) + ["Action"] # Exclude 'id' from header display
        cols = st.columns(len(column_names))

        # Display headers
        for col, header in zip(cols, column_names):
            col.markdown(f"**{header}**")

        # Display rows with remove buttons
        indices_to_remove = []
        ids_to_remove = []
        for index, row in display_df_data.iterrows():
             row_cols = st.columns(len(column_names)) # Match number of header columns
             # Display data columns (excluding 'id')
             for i, col_name in enumerate(display_df_data.columns[:-1]): # Iterate through data columns
                  row_cols[i].write(row[col_name])

             # Add remove button in the last column
             remove_button_key = f"remove_{row['id']}"
             if row_cols[-1].button("🗑️ Remove", key=remove_button_key, help="Remove this item"):
                  ids_to_remove.append(row['id'])
                  # Use rerun to refresh the list immediately after removal
                  st.rerun()

        # Remove selected items outside the loop based on ID
        if ids_to_remove:
             st.session_state.calculations = [
                 item for item in st.session_state.calculations if item['id'] not in ids_to_remove
             ]
             # Rerun is likely already triggered by the button click


        # --- Clear All Button ---
        if st.button("Clear All Calculations", type="secondary"):
             st.session_state.calculations = []
             st.rerun() # Rerun to clear the table
    else:
        st.info("No items added yet. Configure a service above.") # Updated message

    # --- Display Final Summary ---
    display_summary(st.session_state.calculations)

# This replaces the original terminal execution part
if __name__ == '__main__':
    # The caching wrappers are defined above main_st now
    main_st() # Run the streamlit app
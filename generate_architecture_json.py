import os
import json
import re
from openai import OpenAI
import google.generativeai as genai
from mistralai import Mistral
from dotenv import load_dotenv
from colorama import init, Fore, Style
from datetime import datetime

# Initialize colorama
init()

# Load environment variables
load_dotenv()

def print_colored(text, color=Fore.WHITE):
    """Print text with specified color"""
    print(f"{color}{text}{Style.RESET_ALL}")
    return text

def print_success(text):
    """Print success message in green"""
    return print_colored(f"\n{text}", Fore.GREEN)

def print_error(text):
    """Print error message in red"""
    return print_colored(f"\n{text}", Fore.RED)

def print_info(text):
    """Print info message in blue"""
    return print_colored(f"\n{text}", Fore.BLUE)

def is_valid_api_key(api_key):
    """Check if the API key is valid"""
    return api_key and api_key != "your_openai_api_key_here" and api_key != "your_gemini_api_key_here" and api_key != "your_mistral_api_key_here"

# Initialize API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# Initialize API clients
openai_client = None
gemini_model = None
mistral_client = None
active_api = None

# Initialize OpenAI client if API key is available and valid
if is_valid_api_key(OPENAI_API_KEY):
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        active_api = "openai"
    except Exception as e:
        print_error(f"Error initializing OpenAI: {str(e)}")

# Initialize Gemini if OpenAI is not available and Gemini key is valid
elif is_valid_api_key(GEMINI_API_KEY):
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('models/gemini-2.0-pro-exp')
        active_api = "gemini"
    except Exception as e:
        print_error(f"Error initializing Gemini: {str(e)}")

# Initialize Mistral if neither OpenAI nor Gemini are available
elif is_valid_api_key(MISTRAL_API_KEY):
    try:
        mistral_client = Mistral(api_key=MISTRAL_API_KEY)
        active_api = "mistral"
    except Exception as e:
        print_error(f"Error initializing Mistral: {str(e)}")

def generate_with_openai(prompt, system_message):
    """Generate response using OpenAI API"""
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

def generate_with_gemini(prompt, system_message):
    """Generate response using Gemini API"""
    full_prompt = f"{system_message}\n\n{prompt}"
    response = gemini_model.generate_content(full_prompt)
    return response.text

def generate_with_mistral(prompt, system_message):
    """Generate response using Mistral API"""
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]
    try:
        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        print_error(f"Mistral API error: {str(e)}")
        raise

def get_ai_response(prompt, system_message):
    """Get response from the active AI model"""
    try:
        if active_api == "openai" and openai_client:
            print_colored(f"\nUsing OpenAI GPT-4 model", Fore.CYAN)
            response = openai_client.chat.completions.create(
                model="gpt-4o-2024-11-20",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        elif active_api == "gemini" and gemini_model:
            print_colored(f"\nUsing Google Gemini Pro model", Fore.CYAN)
            full_prompt = f"{system_message}\n\n{prompt}"
            response = gemini_model.generate_content(full_prompt)
            return response.text
        elif active_api == "mistral" and mistral_client:
            print_colored(f"\nUsing Mistral Large model", Fore.CYAN)
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
            response = mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=messages
            )
            return response.choices[0].message.content
        else:
            raise Exception("No valid API clients available. Please check your API keys and try again.")
    except Exception as e:
        print_error(f"Error getting AI response: {str(e)}")
        raise

def save_architecture_json(project_title, architecture_json):
    """Save architecture JSON to a file"""
    # Create a safe project title for folder name
    safe_title = "".join(c for c in project_title if c.isalnum() or c in (' ', '-', '_')).strip()
    
    # Create project folder if it doesn't exist
    project_folder = os.path.join(os.getcwd(), safe_title)
    if not os.path.exists(project_folder):
        os.makedirs(project_folder)
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_title}_Architecture_{timestamp}.json"
    
    # Save file in the project folder
    file_path = os.path.join(project_folder, filename)
    with open(file_path, "w", encoding='utf-8') as f:
        json.dump(architecture_json, f, indent=4)
    
    return file_path

def generate_architecture_json(architecture_prompt, template_json):
    """Generate architecture JSON based on prompt and template"""
    context = f"""Based on the following AWS architecture requirements:
{architecture_prompt}

Considering these requirements, please generate an AWS architecture in JSON format, structured similarly to this example:
{json.dumps(template_json, indent=2)}

Ensure the architecture is optimized for low latency, high availability, and cost efficiency."""

    system_message = """You are an AWS architecture expert. Generate a detailed architecture JSON that follows the provided template structure.
Include all necessary AWS services, their configurations, and interconnections.
Focus on creating a well-optimized, secure, and scalable architecture."""

    try:
        response = get_ai_response(context, system_message)
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except Exception as e:
        print_error(f"Error generating architecture JSON: {str(e)}")
        return None

def main():
    """Main function to generate architecture JSON"""
    try:
        # Get project title
        project_title = input("\nEnter the project title: ").strip()
        
        # Read architecture prompt
        prompt_file = input("\nEnter the path to the architecture prompt file: ").strip()
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                architecture_prompt = f.read()
        except Exception as e:
            print_error(f"Error reading prompt file: {str(e)}")
            return
        
        # Read template JSON
        template_file = "templet_arch.json"
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                template_json = json.load(f)
        except Exception as e:
            print_error(f"Error reading template file: {str(e)}")
            return
        
        # Generate architecture JSON
        print_info("\nGenerating architecture JSON...")
        architecture_json = generate_architecture_json(architecture_prompt, template_json)
        
        if architecture_json:
            # Save the generated JSON
            json_file = save_architecture_json(project_title, architecture_json)
            print_success(f"\nArchitecture JSON saved to: {json_file}")
        else:
            print_error("Failed to generate architecture JSON")
        
    except Exception as e:
        print_error(f"An error occurred: {str(e)}")
        print_info("Please try again or contact support if the issue persists.")

if __name__ == "__main__":
    main() 
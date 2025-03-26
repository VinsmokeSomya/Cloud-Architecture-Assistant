import os  # Importing the os module for environment variable access
from openai import OpenAI  # Updated OpenAI import
import google.generativeai as genai  # Importing the Google Generative AI client
from mistralai.client import MistralClient  # Importing the Mistral API client
from mistralai.models.chat_completion import ChatMessage  # Importing the ChatMessage model from Mistral
from dotenv import load_dotenv  # Importing the dotenv module to load environment variables from a .env file
from colorama import init, Fore, Style
from datetime import datetime
import time

# Initialize colorama
init()

# Load environment variables
load_dotenv()

def print_colored(text, color=Fore.WHITE):
    """Print text with specified color"""
    print(f"{color}{text}{Style.RESET_ALL}")
    return text  # Return the text for logging

def print_header(text):
    """Print header text in cyan"""
    return print_colored(f"\n{text}", Fore.CYAN)

def print_question(text):
    """Print question text in yellow"""
    return print_colored(f"\n{text}", Fore.YELLOW)

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
    """Check if the API key is valid (not the default placeholder)"""
    return api_key and api_key != "your_openai_api_key_here" and api_key != "your_gemini_api_key_here" and api_key != "your_mistral_api_key_here"

# Initialize API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# Initialize API clients
openai_client = None
gemini_model = None
mistral_client = None
active_api = None  # Track which API is active

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
        gemini_model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
        active_api = "gemini"
    except Exception as e:
        print_error(f"Error initializing Gemini: {str(e)}")

# Initialize Mistral if neither OpenAI nor Gemini are available
elif is_valid_api_key(MISTRAL_API_KEY):
    try:
        mistral_client = MistralClient(api_key=MISTRAL_API_KEY)
        active_api = "mistral"
    except Exception as e:
        print_error(f"Error initializing Mistral: {str(e)}")

def save_file(project_title, content, file_type):
    """Save content to a file with project title and timestamp"""
    # Create a filename from the project title (remove special characters)
    safe_title = "".join(c for c in project_title if c.isalnum() or c in (' ', '-', '_')).strip()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_title}_{file_type}_{timestamp}.txt"
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(content)
    
    return filename

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
    full_prompt = f"{system_message}\n\n{prompt}"  # Combine system message and user prompt
    response = gemini_model.generate_content(full_prompt)  # Generate content using Gemini model
    return response.text  # Return the generated text

def generate_with_mistral(prompt, system_message):
    """Generate response using Mistral API"""
    messages = [
        ChatMessage(role="system", content=system_message),  # Add system message
        ChatMessage(role="user", content=prompt)  # Add user prompt
    ]
    response = mistral_client.chat(
        model="open-mixtral-8x22b",  # Using the most powerful model
        messages=messages  # Pass the messages to the chat method
    )
    return response.choices[0].message.content  # Return the generated content

def get_active_model():
    """Get the active model that will be used for responses"""
    if active_api == "openai":
        return "OpenAI GPT-3.5"
    elif active_api == "gemini":
        return "Google Gemini"
    elif active_api == "mistral":
        return "Mistral AI (Mixtral-8x7B)"
    return None

def get_project_details():
    """Get initial project details from user"""
    conversation = []
    conversation.append(print_header("\n=== Cloud Architecture Design Assistant ==="))
    conversation.append(print_info("Hi! I'm your cloud architecture consultant. I'll help you design the perfect AWS infrastructure for your project."))
    conversation.append(print_info("Let's start by getting to know your project better."))
    
    project_title = input("\nWhat's the name of your project or startup? ")
    conversation.append(f"\nProject Title: {project_title}")
    
    project_description = input("\nCould you tell me a bit about what your project does? ")
    conversation.append(f"\nProject Description: {project_description}")
    
    return {
        "title": project_title,
        "description": project_description
    }, conversation

def get_next_question(project_details, previous_questions, previous_answers):
    """Generate the next relevant question based on previous context"""
    context = f"""Project Title: {project_details['title']}
Description: {project_details['description']}

Previous Questions and Answers:
{chr(10).join(f"Q: {q}\nA: {a}\n" for q, a in zip(previous_questions, previous_answers))}

Generate the next most relevant question to ask about the project's technical requirements for AWS cloud architecture.
The question should be natural and conversational, as if you're a real architecture engineer having a discussion.
Focus on gathering information about:
1. Expected user base and traffic
2. Data storage requirements
3. Security and compliance needs
4. Performance requirements
5. Budget constraints
6. Scalability needs
7. Integration requirements
8. Disaster recovery needs
9. Monitoring and maintenance preferences
10. Technical stack preferences

Generate only ONE question, and make it sound natural and conversational."""

    system_message = """You are an experienced cloud architecture engineer having a natural conversation with a client.
Your goal is to gather technical requirements by asking one question at a time in a conversational manner.
Make your questions sound natural and friendly, as if you're having a real discussion."""

    return get_ai_response(context, system_message)

def get_user_response(question):
    """Get user response to a single question"""
    while True:
        try:
            response = input("\nYour answer: ").strip()
            
            if not response:
                print_error("I need your input to help design the best architecture for your project. Could you please provide an answer?")
                continue
            
            return response
            
        except KeyboardInterrupt:
            print_error("\nWould you like to start over? (yes/no)")
            if input().lower() != 'yes':
                print_info("Exiting program.")
                return None
            return "RESTART"

def generate_architecture_prompt(project_details, questions, answers):
    """Generate the final architecture prompt based on all gathered information"""
    context = f"""Project Title: {project_details['title']}
Description: {project_details['description']}

Full Requirements Discussion:
{chr(10).join(f"Q: {q}\nA: {a}\n" for q, a in zip(questions, answers))}

Generate a comprehensive AWS architecture prompt in a narrative format with single line breaks between paragraphs.
The prompt should follow this structure but be written in a natural, conversational way:

1. Start with "I am looking for a cloud architecture with AWS components for [project type]"
2. Describe the business requirements and growth projections
3. Detail the technical stack and deployment preferences
4. Explain the resource scaling and performance requirements
5. Outline security, compliance, and disaster recovery needs
6. Specify integration and API requirements
7. Conclude with a request for AWS architecture in JSON format

Make sure to:
1. Include all the technical details but present them in a narrative format
2. Use single line breaks between paragraphs (not double line breaks)
3. Keep each paragraph focused on a specific aspect of the requirements
4. Make the text flow naturally while maintaining readability"""

    system_message = """You are a cloud architecture expert creating detailed AWS infrastructure requirements.
Write the prompt in a natural, flowing style that captures all the technical requirements while maintaining readability.
Use single line breaks between paragraphs for better formatting."""

    return get_ai_response(context, system_message)

def get_ai_response(prompt, system_message):
    """Get response from the active AI model"""
    try:
        if active_api == "openai" and openai_client:
            return generate_with_openai(prompt, system_message)
        elif active_api == "gemini" and gemini_model:
            return generate_with_gemini(prompt, system_message)
        elif active_api == "mistral" and mistral_client:
            return generate_with_mistral(prompt, system_message)
        else:
            raise Exception("No valid API clients available. Please check your API keys and try again.")
    except Exception as e:
        print_error(f"Error getting AI response: {str(e)}")
        raise

def main():
    try:
        # Check for valid API keys
        if not any([openai_client, is_valid_api_key(GEMINI_API_KEY), is_valid_api_key(MISTRAL_API_KEY)]):
            print_error("Error: No valid API keys found. Please add at least one valid API key to your .env file.")
            return

        # Show which AI model is active at startup
        active_model = get_active_model()
        if active_model:
            print_info(f"Using {active_model} for intelligent responses.")

        # Get initial project details
        project_details, conversation = get_project_details()
        
        # Initialize lists for questions and answers
        questions = []
        answers = []
        
        # Get 10 questions and answers one by one
        total_questions = 10
        print_info("\nI'll ask you 10 questions about your project requirements.")
        time.sleep(1)  # Brief pause for readability
        
        # Get questions and answers one by one
        for i in range(total_questions):
            conversation.append(print_header("\n" + "="*50))
            conversation.append(print_info(f"Question {i+1} of {total_questions}"))
            conversation.append(print_header("="*50))
            
            # Get next question with a brief pause
            print_info("\nAnalyzing previous responses...")
            time.sleep(0.5)  # Brief pause for natural flow
            question = get_next_question(project_details, questions, answers)
            questions.append(question)
            print_question(question)
            conversation.append(question)
            
            # Get user response
            answer = get_user_response(question)
            if answer is None:  # User wants to exit
                return
            if answer == "RESTART":  # User wants to start over
                main()
                return
            answers.append(answer)
            conversation.append(f"\nYour answer: {answer}")
        
        # Generate final architecture prompt
        print_info("\nAnalyzing your requirements and generating architecture prompt...")
        time.sleep(1)  # Simulate processing
        
        architecture_prompt = generate_architecture_prompt(project_details, questions, answers)
        
        # Save files
        conversation_filename = save_file(project_details['title'], "\n".join(conversation), "Communication")
        architecture_filename = save_file(project_details['title'], architecture_prompt, "Architecture")
        
        # Final success messages
        print_success("\nGreat! I've generated a comprehensive architecture prompt based on our discussion.")
        print_info(f"The complete conversation has been saved to '{conversation_filename}'")
        print_info(f"The architecture prompt has been saved to '{architecture_filename}'")
        
    except Exception as e:
        print_error(f"An error occurred: {str(e)}")
        print_info("Please try running the program again.")

if __name__ == "__main__":
    main()  # Run the main function
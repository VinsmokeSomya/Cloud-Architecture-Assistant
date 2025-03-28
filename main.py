import os  # Importing the os module for environment variable access
from openai import OpenAI  # Updated OpenAI import
import google.generativeai as genai  # Importing the Google Generative AI client
from mistralai.client import MistralClient  # Importing the Mistral API client
from mistralai.models.chat_completion import ChatMessage  # Importing the ChatMessage model from Mistral
from dotenv import load_dotenv  # Importing the dotenv module to load environment variables from a .env file
from colorama import init, Fore, Style
from datetime import datetime
import time
from mistralai.models.chat_completion import ChatMessage as MistralChatMessage  # Alternative import

# Add new imports
import json
import re
from typing import Dict, List, Optional

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
        gemini_model = genai.GenerativeModel('models/gemini-2.0-pro-exp')
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
    # Create a safe project title for folder name (remove special characters)
    safe_title = "".join(c for c in project_title if c.isalnum() or c in (' ', '-', '_')).strip()
    
    # Create project folder if it doesn't exist
    project_folder = os.path.join(os.getcwd(), safe_title)
    if not os.path.exists(project_folder):
        os.makedirs(project_folder)
    
    # Create a filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_title}_{file_type}_{timestamp}.txt"
    
    # Save file in the project folder
    file_path = os.path.join(project_folder, filename)
    with open(file_path, "w", encoding='utf-8') as f:
        f.write(content)
    
    return file_path

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
        ChatMessage(role="system", content=system_message),
        ChatMessage(role="user", content=prompt)
    ]
    try:
        response = mistral_client.chat(
            model="mistral-tiny",
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        print_error(f"Mistral API error: {str(e)}")
        raise

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

def generate_security_assessment(architecture_prompt: str) -> Dict:
    """Generate security assessment for the proposed architecture"""
    context = f"""Based on the following AWS architecture, provide a detailed security assessment:
{architecture_prompt}

Generate a JSON response with the following structure:
{{
    "security_score": float,
    "risk_level": string,
    "vulnerabilities": [string],
    "recommendations": [string],
    "compliance": {{
        "standards": [string],
        "gaps": [string],
        "remediation_steps": [string]
    }}
}}"""

    system_message = """You are an AWS security expert. Provide detailed security assessment and recommendations.
Focus on AWS security best practices and compliance requirements."""

    try:
        response = get_ai_response(context, system_message)
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except Exception as e:
        print_error(f"Error generating security assessment: {str(e)}")
        return None

def save_analysis_results(project_title: str, architecture_prompt: str, cost_estimate: Optional[Dict], security_assessment: Optional[Dict]):
    """Save all analysis results to files"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save architecture
    architecture_filename = save_file(project_title, architecture_prompt, "Architecture")
    
    # Save cost estimate
    if cost_estimate:
        cost_filename = save_file(project_title, json.dumps(cost_estimate, indent=2), "CostEstimate")
        print_info(f"Cost estimate has been saved to '{cost_filename}'")
    
    # Save security assessment
    if security_assessment:
        security_filename = save_file(project_title, json.dumps(security_assessment, indent=2), "SecurityAssessment")
        print_info(f"Security assessment has been saved to '{security_filename}'")
    
    return architecture_filename  # Return the architecture filename

def analyze_requirements(project_details, questions, answers):
    """Analyze and display understanding of project requirements"""
    context = f"""Project Title: {project_details['title']}
Description: {project_details['description']}

Full Requirements Discussion:
{chr(10).join(f"Q: {q}\nA: {a}\n" for q, a in zip(questions, answers))}

Based on the provided information, analyze and summarize your understanding of the project requirements.
Focus on:
1. Project Scope and Purpose
2. Key Technical Requirements
3. Business Constraints
4. Performance Expectations
5. Security Needs
6. Scalability Requirements
7. Budget Considerations
8. Integration Points
9. Disaster Recovery Needs
10. Monitoring Preferences

Present your understanding in a clear, structured format."""

    system_message = """You are an experienced cloud architecture engineer analyzing project requirements.
Provide a clear, structured summary of your understanding of the project needs and constraints."""

    return get_ai_response(context, system_message)

def modify_answers(questions, answers):
    """Allow user to modify specific answers"""
    while True:
        print_header("\n=== Modify Answers ===")
        print_info("Here are your previous answers:")
        for i, (q, a) in enumerate(zip(questions, answers), 1):
            print_info(f"\n{i}. Question: {q}")
            print_info(f"   Current Answer: {a}")
        
        try:
            answer_num = input("\nEnter the number of the answer you want to modify (or 'done' to finish): ").strip()
            
            if answer_num.lower() == 'done':
                break
                
            answer_num = int(answer_num)
            if 1 <= answer_num <= len(answers):
                print_question(f"\nCurrent question: {questions[answer_num-1]}")
                print_info(f"Current answer: {answers[answer_num-1]}")
                new_answer = input("\nEnter your new answer: ").strip()
                
                if new_answer:
                    answers[answer_num-1] = new_answer
                    print_success("Answer updated successfully!")
                else:
                    print_error("Answer cannot be empty. Keeping the previous answer.")
            else:
                print_error("Invalid number. Please enter a number between 1 and " + str(len(answers)))
                
        except ValueError:
            print_error("Please enter a valid number or 'done'")
            
    return answers

def determine_question_count(project_details):
    """Determine the number of questions based on project complexity"""
    # Analyze project description for complexity indicators
    description = project_details['description'].lower()
    
    # Count complexity indicators
    complexity_score = 0
    
    # Technical complexity indicators
    tech_indicators = [
        'microservices', 'distributed', 'real-time', 'machine learning', 'ai', 'iot',
        'big data', 'analytics', 'streaming', 'container', 'kubernetes', 'serverless',
        'multi-region', 'global', 'enterprise', 'mission-critical', 'high availability',
        'disaster recovery', 'compliance', 'security', 'encryption', 'authentication',
        'authorization', 'api', 'integration', 'database', 'cache', 'queue', 'message',
        'event-driven', 'batch processing', 'data warehouse', 'data lake'
    ]
    
    for indicator in tech_indicators:
        if indicator in description:
            complexity_score += 1
    
    # Determine question count based on complexity score
    if complexity_score <= 5:
        return 10  # Basic project
    elif complexity_score <= 10:
        return 15  # Moderate complexity
    elif complexity_score <= 15:
        return 20  # Complex project
    elif complexity_score <= 20:
        return 25  # Very complex project
    else:
        return 30  # Highly complex project

def main():
    """Main function to run the cloud architecture assistant"""
    try:
        # Get initial project details
        project_details, conversation = get_project_details()
        
        # Create project folder
        safe_title = "".join(c for c in project_details['title'] if c.isalnum() or c in (' ', '-', '_')).strip()
        project_folder = os.path.join(os.getcwd(), safe_title)
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
            print_success(f"\nCreated project folder: {project_folder}")
        
        # Initialize lists for questions and answers
        questions = []
        answers = []
        
        # Get project requirements through conversation
        while True:
            # Generate next question
            next_question = get_next_question(project_details, questions, answers)
            if not next_question:
                break
                
            # Add question to list
            questions.append(next_question)
            conversation.append(print_question(next_question))
            
            # Get user response
            user_response = get_user_response(next_question)
            if user_response == "RESTART":
                return main()
            if not user_response:
                break
                
            # Add answer to list
            answers.append(user_response)
            conversation.append(f"\nYour answer: {user_response}")
            
            # Ask if user wants to continue
            if input("\nWould you like to provide more details? (yes/no): ").lower() != 'yes':
                break
        
        # Generate architecture prompt
        architecture_prompt = generate_architecture_prompt(project_details, questions, answers)
        if not architecture_prompt:
            print_error("Failed to generate architecture prompt")
            return
        
        # Generate security assessment
        security_assessment = generate_security_assessment(architecture_prompt)
        
        # Save conversation history
        conversation_text = "\n".join(conversation)
        conversation_file = save_file(project_details['title'], conversation_text, "Communication")
        print_success(f"\nConversation saved to: {conversation_file}")
        
        # Save architecture prompt
        architecture_file = save_file(project_details['title'], architecture_prompt, "Architecture")
        print_success(f"Architecture prompt saved to: {architecture_file}")
        
        # Save security assessment if available
        if security_assessment:
            security_text = json.dumps(security_assessment, indent=2)
            security_file = save_file(project_details['title'], security_text, "Security")
            print_success(f"Security assessment saved to: {security_file}")
        
        print_success("\nThank you for using the Cloud Architecture Assistant!")
        print_info("Your architecture design and assessment have been saved to files.")
        
    except Exception as e:
        print_error(f"An error occurred: {str(e)}")
        print_info("Please try again or contact support if the issue persists.")

if __name__ == "__main__":
    main()
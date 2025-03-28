import os
import json
import re
import gradio as gr
from openai import OpenAI
import google.generativeai as genai
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from dotenv import load_dotenv
from datetime import datetime
import time

# Load environment variables
load_dotenv()

# Initialize API keys and clients
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# Initialize API clients
openai_client = None
gemini_model = None
mistral_client = None
active_api = None

# Global variables for conversation state
conversation_history = []
questions = []
answers = []
current_project = None

def initialize_api_clients():
    """Initialize API clients based on available keys"""
    global active_api, openai_client, gemini_model, mistral_client
    
    status_messages = []
    
    # Try OpenAI first
    if is_valid_api_key(OPENAI_API_KEY):
        try:
            openai_client = OpenAI(api_key=OPENAI_API_KEY)
            active_api = "openai"
            return "✅ OpenAI API initialized successfully"
        except Exception as e:
            status_messages.append(f"❌ OpenAI API Error: {str(e)}")
    else:
        status_messages.append("❌ OpenAI API: No valid API key found")
    
    # Try Gemini next
    if is_valid_api_key(GEMINI_API_KEY):
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            gemini_model = genai.GenerativeModel('models/gemini-2.0-pro-exp')  # Using more stable model
            active_api = "gemini"
            return "✅ Gemini API initialized successfully"
        except Exception as e:
            status_messages.append(f"❌ Gemini API Error: {str(e)}")
    else:
        status_messages.append("❌ Gemini API: No valid API key found")
    
    # Try Mistral last
    if is_valid_api_key(MISTRAL_API_KEY):
        try:
            mistral_client = MistralClient(api_key=MISTRAL_API_KEY)
            active_api = "mistral"
            return "✅ Mistral API initialized successfully"
        except Exception as e:
            status_messages.append(f"❌ Mistral API Error: {str(e)}")
    else:
        status_messages.append("❌ Mistral API: No valid API key found")
    
    return "\n".join([
        "❌ No APIs available. Please configure at least one API key in the .env file:",
        "1. Get an API key from OpenAI, Google Gemini, or Mistral",
        "2. Add it to the .env file",
        "3. Click 'Retry API Connection'",
        "",
        "Status:",
        *status_messages
    ])

def is_valid_api_key(api_key):
    """Check if the API key is valid"""
    if not api_key:
        return False
    if api_key in ["your_openai_api_key_here", "your_gemini_api_key_here", "your_mistral_api_key_here"]:
        return False
    return True

def get_ai_response(prompt, system_message):
    """Get response from the active AI model with fallback mechanisms"""
    global active_api
    
    def try_api_call():
        try:
            if active_api == "openai" and openai_client:
                response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content, None
            elif active_api == "gemini" and gemini_model:
                full_prompt = f"{system_message}\n\n{prompt}"
                response = gemini_model.generate_content(full_prompt)
                return response.text, None
            elif active_api == "mistral" and mistral_client:
                messages = [
                    ChatMessage(role="system", content=system_message),
                    ChatMessage(role="user", content=prompt)
                ]
                response = mistral_client.chat(
                    model="mistral-tiny",
                    messages=messages
                )
                return response.choices[0].message.content, None
            return None, "No valid API clients available"
        except Exception as e:
            return None, str(e)

    # Try current API first
    response, error = try_api_call()
    if response:
        return response

    # If current API fails, try other available APIs
    original_api = active_api
    apis_to_try = ["openai", "mistral", "gemini"]
    
    for api in apis_to_try:
        if api != original_api:
            active_api = api
            response, new_error = try_api_call()
            if response:
                return response
            error = f"{error}\nTried {api}: {new_error}"

    # If all APIs fail, raise exception with all errors
    raise Exception(f"All API calls failed: {error}")

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
7. Conclude with a request for AWS architecture in JSON format"""

    system_message = """You are a cloud architecture expert creating detailed AWS infrastructure requirements.
Write the prompt in a natural, flowing style that captures all the technical requirements while maintaining readability."""

    return get_ai_response(context, system_message)

def generate_security_assessment(architecture_prompt):
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
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except Exception as e:
        raise Exception(f"Error generating security assessment: {str(e)}")

def generate_architecture_json_from_prompt(architecture_prompt, template_json):
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
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except Exception as e:
        raise Exception(f"Error generating architecture JSON: {str(e)}")

def save_file(project_title, content, file_type):
    """Save content to a file with project title and timestamp"""
    safe_title = "".join(c for c in project_title if c.isalnum() or c in (' ', '-', '_')).strip()
    project_folder = os.path.join(os.getcwd(), safe_title)
    
    if not os.path.exists(project_folder):
        os.makedirs(project_folder)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_title}_{file_type}_{timestamp}.txt"
    file_path = os.path.join(project_folder, filename)
    
    with open(file_path, "w", encoding='utf-8') as f:
        f.write(content)
    
    return file_path

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

def start_conversation(project_title, project_description):
    """Start a new conversation"""
    global conversation_history, questions, answers, current_project
    
    # Reset conversation state
    conversation_history = []
    questions = []
    answers = []
    current_project = {
        "title": project_title,
        "description": project_description
    }
    
    # Determine total questions based on project complexity
    total_questions = determine_question_count(current_project)
    
    # Get first question
    next_question = get_next_question(current_project, questions, answers)
    if next_question:
        conversation_history.append(f"Assistant: {next_question}")
        questions.append(next_question)
        return "\n".join(conversation_history), next_question, f"Question 1/{total_questions}"
    return "Failed to start conversation", "", f"Question 0/{total_questions}"

def continue_conversation(user_response):
    """Continue the conversation with user's response"""
    global conversation_history, questions, answers
    
    if not current_project:
        return "No active conversation. Please start a new conversation.", ""
    
    # Add user's response
    conversation_history.append(f"User: {user_response}")
    answers.append(user_response)
    
    # Get next question
    next_question = get_next_question(current_project, questions, answers)
    if next_question:
        conversation_history.append(f"Assistant: {next_question}")
        questions.append(next_question)
        return "\n".join(conversation_history), next_question
    return "\n".join(conversation_history), ""

def finish_conversation():
    """Finish the conversation and generate architecture"""
    global conversation_history, questions, answers, current_project
    
    if not current_project:
        return "No active conversation. Please start a new conversation.", ""
    
    try:
        # Generate architecture prompt
        architecture_prompt = generate_architecture_prompt(current_project, questions, answers)
        if not architecture_prompt:
            return "Failed to generate architecture prompt", ""
        
        # Generate security assessment
        security_assessment = generate_security_assessment(architecture_prompt)
        
        # Save all results
        conversation_text = "\n".join(conversation_history)
        save_file(current_project["title"], conversation_text, "Communication")
        save_file(current_project["title"], architecture_prompt, "Architecture")
        
        if security_assessment:
            save_file(current_project["title"], json.dumps(security_assessment, indent=2), "Security")
        
        # Reset conversation state
        conversation_history = []
        questions = []
        answers = []
        current_project = None
        
        return "Architecture generated successfully!", architecture_prompt
        
    except Exception as e:
        return f"An error occurred: {str(e)}", ""

def generate_architecture_json(architecture_prompt, project_title, template_file=None):
    """Generate architecture JSON from prompt"""
    try:
        # Use provided template file or default to templet_arch.json
        template_path = template_file if template_file else "templet_arch.json"
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_json = json.load(f)
        except FileNotFoundError:
            return f"Template file not found: {template_path}", ""
        except json.JSONDecodeError:
            return "Invalid JSON template file", ""
        
        # Generate architecture JSON
        architecture_json = generate_architecture_json_from_prompt(architecture_prompt, template_json)
        
        if architecture_json:
            # Save the JSON
            json_file = save_file(project_title, json.dumps(architecture_json, indent=4), "Architecture")
            return f"Architecture JSON saved to: {json_file}", json.dumps(architecture_json, indent=2)
        else:
            return "Failed to generate architecture JSON", ""
            
    except Exception as e:
        return f"An error occurred: {str(e)}", ""

def create_ui():
    """Create the Gradio UI"""
    with gr.Blocks(title="Cloud Architecture Design Assistant", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# Cloud Architecture Design Assistant")
        gr.Markdown("Design your AWS cloud architecture through an interactive interface.")
        
        # API Status at the top
        with gr.Row():
            with gr.Column(scale=1):
                api_status = gr.Textbox(
                    label="API Status",
                    value=initialize_api_clients(),
                    lines=3,
                    interactive=False
                )
                retry_btn = gr.Button("Retry API Connection", variant="secondary")
                retry_btn.click(fn=initialize_api_clients, inputs=[], outputs=[api_status])
        
        # Store total questions as a state variable
        total_questions = gr.State(value=10)
        
        with gr.Tab("Architecture Design"):
            with gr.Row():
                with gr.Column(scale=1):
                    project_title = gr.Textbox(label="Project Title", placeholder="Enter your project name")
                    project_description = gr.Textbox(label="Project Description", placeholder="Describe your project", lines=3)
                    start_btn = gr.Button("Start Conversation", variant="primary")
            
            with gr.Row():
                # Left side: Current Question and Response
                with gr.Column(scale=1):
                    question_counter = gr.Textbox(
                        label="Progress",
                        value="Question 0/10",
                        interactive=False
                    )
                    current_question = gr.Textbox(
                        label="Current Question",
                        lines=5,
                        interactive=False
                    )
                    user_response = gr.Textbox(
                        label="Your Response",
                        placeholder="Type your answer here...",
                        lines=3
                    )
                    with gr.Row():
                        continue_btn = gr.Button("Continue", variant="primary")
                        finish_btn = gr.Button("Finish & Generate", variant="secondary")
                
                # Right side: Conversation History
                with gr.Column(scale=1):
                    conversation_history = gr.Textbox(
                        label="Conversation History",
                        lines=20,
                        max_lines=100,
                        interactive=False
                    )
            
            # Bottom section: Status and Generated Architecture
            with gr.Row():
                with gr.Column(scale=1):
                    status = gr.Textbox(
                        label="Status",
                        lines=3,
                        interactive=False
                    )
            
            with gr.Row():
                with gr.Column(scale=1):
                    architecture_output = gr.Textbox(
                        label="Generated Architecture Prompt",
                        lines=15,
                        interactive=False,
                        show_copy_button=True
                    )
            
            def update_counter():
                if current_project:
                    total = determine_question_count(current_project)
                    return f"Question {len(questions)}/{total}"
                return "Question 0/10"
            
            def clear_response(response, history, question):
                return "", history, question
            
            start_btn.click(
                fn=start_conversation,
                inputs=[project_title, project_description],
                outputs=[conversation_history, current_question, question_counter]
            )
            
            continue_btn.click(
                fn=continue_conversation,
                inputs=[user_response],
                outputs=[conversation_history, current_question]
            ).then(
                fn=update_counter,
                inputs=None,
                outputs=question_counter
            ).then(
                fn=lambda x: "",
                inputs=[user_response],
                outputs=[user_response]
            )
            
            finish_btn.click(
                fn=finish_conversation,
                inputs=[],
                outputs=[status, architecture_output]
            )
        
        with gr.Tab("Architecture JSON"):
            with gr.Row():
                with gr.Column():
                    json_project_title = gr.Textbox(
                        label="Project Title",
                        placeholder="Enter your project name"
                    )
                    architecture_prompt = gr.Textbox(
                        label="Architecture Prompt",
                        placeholder="Paste your architecture prompt here",
                        lines=5
                    )
                    template_file = gr.File(
                        label="Template JSON (Optional)",
                        file_types=[".json"],
                        type="filepath"
                    )
                    generate_json_btn = gr.Button("Generate JSON", variant="primary")
                
                with gr.Column():
                    json_status = gr.Textbox(
                        label="Status",
                        lines=3,
                        interactive=False
                    )
                    json_output = gr.Textbox(
                        label="Generated JSON",
                        lines=19,
                        interactive=False,
                        show_copy_button=True
                    )
            
            def process_template(template_file):
                if template_file is None:
                    return None
                return template_file.name
            
            generate_json_btn.click(
                fn=lambda p, t, f: generate_architecture_json(p, t, process_template(f)),
                inputs=[architecture_prompt, json_project_title, template_file],
                outputs=[json_status, json_output]
            )
    
    return demo

if __name__ == "__main__":
    demo = create_ui()
    demo.launch(share=True)  # Enable sharing for external access 
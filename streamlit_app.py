import os
import streamlit as st
import json
import re
import time
from typing import Dict, List, Optional
from datetime import datetime

from openai import OpenAI  # Updated OpenAI import
import google.generativeai as genai  # Importing the Google Generative AI client
from mistralai import Mistral  # Updated Mistral import
from dotenv import load_dotenv  # Importing the dotenv module to load environment variables from a .env file
from colorama import init, Fore, Style

# Initialize colorama for console printing in development
init()

# Load environment variables
load_dotenv()

# Set Streamlit page config
st.set_page_config(
    page_title="AWS Cloud Architecture Assistant",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Helper functions
def is_valid_api_key(api_key):
    """Check if the API key is valid (not the default placeholder)"""
    return api_key and api_key != "your_openai_api_key_here" and api_key != "your_gemini_api_key_here" and api_key != "your_mistral_api_key_here"

def save_file(project_title, content, file_type):
    """Save content to a file with project title and timestamp"""
    # Create a safe folder name from the project title (remove special characters)
    safe_title = "".join(c for c in project_title if c.isalnum() or c in (' ', '-', '_')).strip()
    
    # Create project folder if it doesn't exist
    project_folder = safe_title
    if not os.path.exists(project_folder):
        os.makedirs(project_folder)
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_title}_{file_type}_{timestamp}.txt"
    
    # Full path including project folder
    filepath = os.path.join(project_folder, filename)
    
    with open(filepath, "w", encoding='utf-8') as f:
        f.write(content)
    
    return filepath  # Return the full filepath

def get_ai_response(client, prompt, system_message):
    """Get response from the active AI model"""
    try:
        if client["type"] == "openai":
            response = client["client"].chat.completions.create(
                model="gpt-4o-2024-11-20",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content, None
        elif client["type"] == "gemini":
            full_prompt = f"{system_message}\n\n{prompt}"
            response = client["client"].generate_content(full_prompt)
            return response.text, None
        elif client["type"] == "mistral":
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
            response = client["client"].chat.complete(
                model="mistral-large-latest",
                messages=messages
            )
            return response.choices[0].message.content, None
        return None, "No valid AI client available"
    except Exception as e:
        return None, str(e)

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

def get_next_question(client, project_details, previous_questions, previous_answers):
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

    response, error = get_ai_response(client, context, system_message)
    if response:
        return response
    else:
        st.error(f"Error getting AI response: {error}")
        return None

def analyze_requirements(client, project_details, questions, answers):
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

    response, error = get_ai_response(client, context, system_message)
    if response:
        return response
    else:
        st.error(f"Error getting AI response: {error}")
        return None

def generate_architecture_prompt(client, project_details, questions, answers):
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

    response, error = get_ai_response(client, context, system_message)
    if response:
        return response
    else:
        st.error(f"Error getting AI response: {error}")
        return None

def generate_security_assessment(client, architecture_prompt: str) -> Dict:
    """Generate security assessment for the proposed architecture"""
    context = f"""Based on the following AWS architecture, provide a security assessment:
{architecture_prompt}

Generate a JSON response with the following structure:
{{
    "security_score": int,
    "vulnerabilities": [string],
    "recommendations": [string],
    "compliance_status": {{
        "hipaa": bool,
        "pci": bool,
        "gdpr": bool,
        "iso27001": bool
    }},
    "security_best_practices": [string]
}}"""

    system_message = """You are an AWS security expert. Provide comprehensive security assessment and recommendations.
Focus on AWS security best practices and compliance requirements."""

    try:
        response, error = get_ai_response(client, context, system_message)
        if response:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        return None
    except Exception as e:
        st.error(f"Error generating security assessment: {str(e)}")
        return None

# Initialize Streamlit session state
if 'step' not in st.session_state:
    st.session_state.step = 'init'
if 'project_details' not in st.session_state:
    st.session_state.project_details = {}
if 'questions' not in st.session_state:
    st.session_state.questions = []
if 'answers' not in st.session_state:
    st.session_state.answers = []
if 'ai_client' not in st.session_state:
    st.session_state.ai_client = None
if 'current_question_idx' not in st.session_state:
    st.session_state.current_question_idx = 0
if 'total_questions' not in st.session_state:
    st.session_state.total_questions = 0
if 'understanding' not in st.session_state:
    st.session_state.understanding = None
if 'architecture_prompt' not in st.session_state:
    st.session_state.architecture_prompt = None
if 'security_assessment' not in st.session_state:
    st.session_state.security_assessment = None
if 'files_saved' not in st.session_state:
    st.session_state.files_saved = {}

# Define callback functions for button clicks
def start_project():
    st.session_state.project_details = {
        'title': st.session_state.project_title,
        'description': st.session_state.project_description
    }
    st.session_state.total_questions = determine_question_count(st.session_state.project_details)
    st.session_state.step = 'confirm_details'
    st.session_state.needs_rerun = True

def confirm_details():
    st.session_state.step = 'questions'
    st.session_state.current_question_idx = 0
    st.session_state.questions = []
    st.session_state.answers = []
    st.session_state.needs_rerun = True

def edit_details():
    # Preserve project details when going back to edit
    if 'project_details' in st.session_state and st.session_state.project_details:
        st.session_state.project_title = st.session_state.project_details.get('title', '')
        st.session_state.project_description = st.session_state.project_details.get('description', '')
    
    # Go back to initial project details page
    st.session_state.step = 'init'
    st.session_state.needs_rerun = True

def submit_answer():
    if st.session_state.answer_input:
        st.session_state.answers.append(st.session_state.answer_input)
        st.session_state.current_question_idx += 1
        
        # Clear the input field after submission
        st.session_state.answer_input = ""
        
        # Check if we've reached the total questions
        if st.session_state.current_question_idx >= st.session_state.total_questions:
            # Generate understanding
            with st.spinner("Analyzing your requirements..."):
                st.session_state.understanding = analyze_requirements(
                    st.session_state.ai_client,
                    st.session_state.project_details,
                    st.session_state.questions,
                    st.session_state.answers
                )
            st.session_state.step = 'understanding'

def confirm_understanding():
    st.session_state.step = 'generate_architecture'

def modify_answers():
    st.session_state.step = 'modify_answers'

def save_modified_answers():
    # Update answers with the modified versions
    for i in range(len(st.session_state.questions)):
        key = f"modified_answer_{i}"
        if key in st.session_state:
            st.session_state.answers[i] = st.session_state[key]
    
    # Regenerate understanding
    with st.spinner("Re-analyzing your requirements with modified answers..."):
        st.session_state.understanding = analyze_requirements(
            st.session_state.ai_client,
            st.session_state.project_details,
            st.session_state.questions,
            st.session_state.answers
        )
    
    st.session_state.step = 'understanding'

def start_over():
    for key in list(st.session_state.keys()):
        if key != 'ai_client':  # Keep AI client initialized
            del st.session_state[key]
    st.session_state.step = 'init'
    st.session_state.questions = []
    st.session_state.answers = []
    st.session_state.current_question_idx = 0

def generate_final_outputs():
    """Generate architecture prompt and security assessment"""
    try:
        # Generate architecture prompt
        with st.spinner("Generating architecture prompt..."):
            st.session_state.architecture_prompt = generate_architecture_prompt(
                st.session_state.ai_client,
                st.session_state.project_details,
                st.session_state.questions,
                st.session_state.answers
            )
            
            # Add debug info
            if not st.session_state.architecture_prompt:
                st.error("Failed to generate architecture prompt. Please check your AI API key or try again.")
                return
                
        # Generate security assessment
        with st.spinner("Performing security assessment..."):
            st.session_state.security_assessment = generate_security_assessment(
                st.session_state.ai_client,
                st.session_state.architecture_prompt
            )
            
            # Add debug info
            if not st.session_state.security_assessment:
                st.warning("Security assessment could not be generated, but we can continue with the architecture.")
        
        # Move to results page
        st.session_state.step = 'results'
        st.session_state.needs_rerun = True
        
    except Exception as e:
        st.error(f"An error occurred during architecture generation: {str(e)}")
        st.info("You can try again or check your API key settings.")

def save_all_results():
    """Save all results to files"""
    files = {}
    
    # Save conversation
    conversation = []
    conversation.append(f"Project: {st.session_state.project_details['title']}")
    conversation.append(f"Description: {st.session_state.project_details['description']}")
    conversation.append("\nRequirements Collection:")
    
    for q, a in zip(st.session_state.questions, st.session_state.answers):
        conversation.append(f"\nQ: {q}")
        conversation.append(f"A: {a}")
    
    conversation_text = "\n".join(conversation)
    conversation_file = save_file(st.session_state.project_details['title'], conversation_text, "Conversation")
    files['conversation'] = conversation_file
    
    # Save architecture
    architecture_file = save_file(st.session_state.project_details['title'], st.session_state.architecture_prompt, "Architecture")
    files['architecture'] = architecture_file
    
    # Save security assessment
    if st.session_state.security_assessment:
        security_file = save_file(
            st.session_state.project_details['title'], 
            json.dumps(st.session_state.security_assessment, indent=2), 
            "SecurityAssessment"
        )
        files['security'] = security_file
    
    st.session_state.files_saved = files
    st.session_state.step = 'download'

# Sidebar for LLM selection
st.sidebar.title("☁️ Cloud Architecture Assistant")
st.sidebar.write("Generate AWS cloud architecture designs with AI assistance")

# LLM Selection in sidebar
st.sidebar.subheader("Select AI Provider")
llm_option = st.sidebar.radio(
    "Choose your preferred AI model:",
    ["OpenAI ChatGPT", "Google Gemini", "Mistral AI"],
    help="Select which AI model to use for generating responses"
)

# API Key input
with st.sidebar.expander("Set API Key", expanded=False):
    if llm_option == "OpenAI ChatGPT":
        openai_key = st.text_input("OpenAI API Key", value=os.getenv("OPENAI_API_KEY", ""), type="password")
        if st.button("Apply OpenAI Key"):
            try:
                client = OpenAI(api_key=openai_key)
                st.session_state.ai_client = {
                    "type": "openai",
                    "client": client,
                    "name": "OpenAI ChatGPT"
                }
                st.sidebar.success("OpenAI API key applied successfully!")
            except Exception as e:
                st.sidebar.error(f"Error with OpenAI API key: {e}")
    
    elif llm_option == "Google Gemini":
        gemini_key = st.text_input("Google Gemini API Key", value=os.getenv("GEMINI_API_KEY", ""), type="password")
        if st.button("Apply Gemini Key"):
            try:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel('models/gemini-2.0-pro-exp')
                st.session_state.ai_client = {
                    "type": "gemini",
                    "client": model,
                    "name": "Google Gemini"
                }
                st.sidebar.success("Gemini API key applied successfully!")
            except Exception as e:
                st.sidebar.error(f"Error with Gemini API key: {e}")
    
    elif llm_option == "Mistral AI":
        mistral_key = st.text_input("Mistral AI API Key", value=os.getenv("MISTRAL_API_KEY", ""), type="password")
        if st.button("Apply Mistral Key"):
            try:
                client = Mistral(api_key=mistral_key)
                st.session_state.ai_client = {
                    "type": "mistral",
                    "client": client,
                    "name": "Mistral AI"
                }
                st.sidebar.success("Mistral API key applied successfully!")
            except Exception as e:
                st.sidebar.error(f"Error with Mistral API key: {e}")

# Show current status in sidebar
if st.session_state.ai_client:
    st.sidebar.success(f"Using {st.session_state.ai_client['name']}")
else:
    st.sidebar.warning("No AI client set up. Please enter your API key.")

# Display progress in sidebar
if st.session_state.step != 'init':
    st.sidebar.subheader("Project Progress")
    project_name = st.session_state.project_details.get('title', 'Project')
    st.sidebar.write(f"Project: {project_name}")
    
    steps = ['Project Setup', 'Requirements', 'Analysis', 'Architecture', 'Security', 'Download']
    current_step_idx = {
        'init': 0,
        'questions': 1,
        'understanding': 2,
        'modify_answers': 2,
        'generate_architecture': 3,
        'results': 4,
        'download': 5
    }.get(st.session_state.step, 0)
    
    progress = (current_step_idx + 1) / len(steps)
    st.sidebar.progress(progress)
    
    step_status = ["✓" if i <= current_step_idx else " " for i in range(len(steps))]
    for i, step in enumerate(steps):
        st.sidebar.write(f"{step_status[i]} {step}")

# Initialize AI on startup
if 'ai_client' not in st.session_state or not st.session_state.ai_client:
    # Try to initialize with environment variables
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    mistral_key = os.getenv("MISTRAL_API_KEY")
    
    if is_valid_api_key(openai_key):
        try:
            client = OpenAI(api_key=openai_key)
            st.session_state.ai_client = {
                "type": "openai",
                "client": client,
                "name": "OpenAI ChatGPT"
            }
        except:
            pass
    elif is_valid_api_key(gemini_key):
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel('models/gemini-2.0-pro-exp')
            st.session_state.ai_client = {
                "type": "gemini",
                "client": model,
                "name": "Google Gemini"
            }
        except:
            pass
    elif is_valid_api_key(mistral_key):
        try:
            client = Mistral(api_key=mistral_key)
            st.session_state.ai_client = {
                "type": "mistral",
                "client": client,
                "name": "Mistral AI"
            }
        except:
            pass

# Main content
if st.session_state.step == 'init':
    # Initial setup page
    st.title("AWS Cloud Architecture Assistant")
    st.write("Welcome! This tool will help you design the perfect AWS infrastructure for your project.")
    
    if not st.session_state.ai_client:
        st.warning("⚠️ Please set up your AI provider API key in the sidebar to continue.")
    
    with st.form("project_details_form"):
        st.header("Project Details")
        st.text_input("Project Title", key="project_title", 
                    help="Enter your project or startup name")
        st.text_area("Project Description", key="project_description", 
                    help="Describe what your project does and its main goals")
        
        start_button = st.form_submit_button("Start Design Process")
        if start_button and st.session_state.ai_client:
            if not st.session_state.project_title or not st.session_state.project_description:
                st.error("Please provide both project title and description.")
            else:
                start_project()
        elif start_button and not st.session_state.ai_client:
            st.error("Please set up your AI provider API key in the sidebar first.")

elif st.session_state.step == 'confirm_details':
    # Confirmation page before starting questions
    st.title("Confirm Project Details")
    st.write("Please review your project details before we start gathering requirements.")
    
    st.subheader("Project Title")
    st.write(st.session_state.project_details['title'])
    
    st.subheader("Project Description")
    st.write(st.session_state.project_details['description'])
    
    st.subheader("Estimated Questions")
    st.write(f"Based on your project description, we'll ask approximately {st.session_state.total_questions} questions to understand your requirements.")
    
    # Add buttons to confirm or edit details
    col1, col2 = st.columns([1, 1])
    with col1:
        st.button("✅ Confirm & Start Questions", on_click=confirm_details)
    with col2:
        st.button("✏️ Edit Details", on_click=edit_details)

elif st.session_state.step == 'questions':
    # Questions page
    st.title("Requirements Collection")
    st.write(f"Question {st.session_state.current_question_idx + 1} of {st.session_state.total_questions}")
    
    # Update the progress indicator with animations on completed segments
    progress_html = """
    <style>
    .progress-container {
        width: 100%;
        height: 8px;
        background-color: #f0f0f0;
        border-radius: 10px;
        margin-bottom: 20px;
        display: flex;
        overflow: hidden;
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
    }
    .progress-segment {
        height: 100%;
        /* Remove width transition - it causes the sizing issue */
    }
    .completed {
        background-color: #ff9d00;  /* Orange for completed */
        position: relative;
        overflow: hidden;
    }
    .completed::after {
        content: "";
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
        animation: shimmer 1.5s infinite;
    }
    .current {
        background-color: #3498db;  /* Change from light green to a nice blue */
        box-shadow: 0 0 5px rgba(52, 152, 219, 0.5);
    }
    .remaining {
        background-color: #eaecee;  /* Very light gray for remaining */
    }
    @keyframes shimmer {
        100% {
            left: 100%;
        }
    }
    </style>
    <div class="progress-container">
    """
    
    # Calculate segment widths
    segment_width = 100 / st.session_state.total_questions
    
    # Add completed segments
    for i in range(st.session_state.current_question_idx):
        progress_html += f'<div class="progress-segment completed" style="width: {segment_width}%;"></div>'
    
    # Add current segment
    progress_html += f'<div class="progress-segment current" style="width: {segment_width}%;"></div>'
    
    # Add remaining segments
    remaining_questions = st.session_state.total_questions - st.session_state.current_question_idx - 1
    if remaining_questions > 0:
        progress_html += f'<div class="progress-segment remaining" style="width: {remaining_questions * segment_width}%;"></div>'
    
    progress_html += "</div>"
    
    # Display the custom progress indicator
    st.markdown(progress_html, unsafe_allow_html=True)
    
    # Generate next question if needed
    if len(st.session_state.questions) <= st.session_state.current_question_idx:
        with st.spinner("Analyzing previous answers..."):
            next_question = get_next_question(
                st.session_state.ai_client,
                st.session_state.project_details,
                st.session_state.questions,
                st.session_state.answers
            )
            st.session_state.questions.append(next_question)
    
    # Display current question and answer box
    current_question = st.session_state.questions[st.session_state.current_question_idx]
    st.subheader(current_question)
    
    # Previous Q&A for context
    if st.session_state.current_question_idx > 0:
        with st.expander("View previous questions and answers", expanded=False):
            for i, (q, a) in enumerate(zip(
                st.session_state.questions[:st.session_state.current_question_idx],
                st.session_state.answers[:st.session_state.current_question_idx]
            )):
                st.write(f"**Q{i+1}:** {q}")
                st.write(f"**A{i+1}:** {a}")
                st.write("---")
    
    # Answer input
    st.text_area("Your answer:", key="answer_input", height=100)
    
    # Define validation function
    def validate_and_submit():
        if st.session_state.answer_input.strip():
            submit_answer()
        else:
            st.session_state.show_error = True
    
    # Use on_click callback for button
    col1, col2 = st.columns([1, 6])
    with col1:
        st.button("Submit", on_click=validate_and_submit)
    
    # Display error if needed
    if 'show_error' in st.session_state and st.session_state.show_error:
        st.error("Please provide an answer to continue.")
        st.session_state.show_error = False

elif st.session_state.step == 'understanding':
    # Understanding review page
    st.title("Requirements Analysis")
    st.write("Below is my understanding of your project requirements based on our discussion:")
    
    st.markdown(st.session_state.understanding)
    
    # Confirmation buttons with on_click callbacks
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.button("✅ Confirm and Continue", on_click=confirm_understanding)
    with col2:
        st.button("🔄 Modify Answers", on_click=modify_answers)
    with col3:
        st.button("🔁 Start Over", on_click=start_over)

elif st.session_state.step == 'modify_answers':
    # Modify answers page
    st.title("Modify Your Answers")
    st.write("Review and edit your answers if needed:")
    
    with st.form("modify_answers_form"):
        for i, (question, answer) in enumerate(zip(st.session_state.questions, st.session_state.answers)):
            st.subheader(f"Question {i+1}:")
            st.write(question)
            st.text_area("Your answer:", key=f"modified_answer_{i}", value=answer, height=100)
            st.write("---")
        
        st.form_submit_button("Save Changes", on_click=save_modified_answers)

elif st.session_state.step == 'generate_architecture':
    # Generate architecture page
    st.title("Generating Cloud Architecture")
    
    with st.spinner("Please wait while we design your architecture..."):
        generate_final_outputs()

elif st.session_state.step == 'results':
    # Results display page
    st.title("Your AWS Cloud Architecture")
    
    # Architecture prompt
    st.subheader("Architecture Requirements")
    st.write(st.session_state.architecture_prompt)
    
    # Security assessment
    if st.session_state.security_assessment:
        st.subheader("Security Assessment")
        
        score = st.session_state.security_assessment.get('security_score', 0)
        
        # Display score with a gauge or progress bar
        col1, col2 = st.columns([1, 3])
        with col1:
            st.metric("Security Score", f"{score}/100")
        with col2:
            # Color code the score
            if score >= 80:
                color = "green"
            elif score >= 60:
                color = "orange"
            else:
                color = "red"
            st.markdown(f"""
            <div style="background-color: #f0f0f0; border-radius: 10px; padding: 10px; margin-bottom: 10px;">
                <div style="background-color: {color}; width: {score}%; height: 20px; border-radius: 5px;"></div>
            </div>
            """, unsafe_allow_html=True)
        
        # Display vulnerabilities
        st.subheader("Vulnerabilities Identified")
        for vuln in st.session_state.security_assessment.get('vulnerabilities', []):
            st.markdown(f"- {vuln}")
        
        # Display recommendations
        st.subheader("Security Recommendations")
        for rec in st.session_state.security_assessment.get('recommendations', []):
            st.markdown(f"- {rec}")
        
        # Display compliance status
        st.subheader("Compliance Status")
        compliance = st.session_state.security_assessment.get('compliance_status', {})
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.write("HIPAA", "✅" if compliance.get('hipaa', False) else "❌")
        with col2:
            st.write("PCI DSS", "✅" if compliance.get('pci', False) else "❌")
        with col3:
            st.write("GDPR", "✅" if compliance.get('gdpr', False) else "❌")
        with col4:
            st.write("ISO 27001", "✅" if compliance.get('iso27001', False) else "❌")
    
    # Save results button with on_click callback
    st.button("Save Results", on_click=save_all_results)

elif st.session_state.step == 'download':
    # Download page
    st.title("Your Files Are Ready!")
    st.write("Your architecture design and analysis files have been saved.")
    
    st.success("All files have been saved successfully!")
    
    # Create download buttons for each file
    for file_type, filepath in st.session_state.files_saved.items():
        filename = os.path.basename(filepath)
        
        # Read file contents for download
        with open(filepath, 'r') as f:
            file_contents = f.read()
        
        # Create download button
        st.download_button(
            label=f"Download {file_type.capitalize()} File",
            data=file_contents,
            file_name=filename,
            mime="text/plain"
        )
    
    # Options to continue with on_click callbacks
    col1, col2 = st.columns(2)
    with col1:
        # Reset show_exit flag when starting new project
        def reset_and_start_over():
            st.session_state.show_exit = False
            start_over()
            
        st.button("Start a New Project", on_click=reset_and_start_over)
    with col2:
        # Only show balloons if not already shown
        def show_exit_message():
            if 'balloons_shown' not in st.session_state:
                st.session_state.balloons_shown = True
                st.session_state.show_exit = True
            
        st.button("Exit", on_click=show_exit_message)
        
        # Only trigger balloons once when exit is clicked
        if 'show_exit' in st.session_state and st.session_state.show_exit and 'balloons_shown' in st.session_state:
            st.balloons()
            st.write("Thank you for using the AWS Cloud Architecture Assistant!")
            # Reset after showing
            st.session_state.show_exit = False

# Add a check for needs_rerun at the end of the script (add this as the very last line of the file)
# Add this check just before the footer
if 'needs_rerun' in st.session_state and st.session_state.needs_rerun:
    st.session_state.needs_rerun = False
    st.rerun()

# The footer should remain below this check
st.markdown("---")
st.markdown("☁️ Cloud Architecture Assistant| © 2024") 
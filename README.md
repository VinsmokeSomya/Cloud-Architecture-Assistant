# Cloud Architecture Assistant - Streamlit Interface

This Streamlit app provides a web interface for the Cloud Architecture Assistant, helping users design AWS cloud architectures with AI assistance.

## Features

- Interactive web interface for designing cloud architectures
- Multi-step process: project details → requirements collection → architecture generation → security assessment
- Support for OpenAI, Google Gemini, and Mistral AI models
- Security scoring and compliance recommendations
- Export options for all generated content

## Installation

1. Install the required packages:

```bash
pip install -r requirements.txt
```

2. Set up your API keys:
   - Create a `.env` file in the project root
   - Add your API keys (at least one is required):
   
```
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
MISTRAL_API_KEY=your_mistral_api_key_here
```

## Running the App

Start the Streamlit app with:

```bash
streamlit run streamlit_app.py
```

This will launch the web interface in your default browser.

## Usage

1. **Select AI Provider**: Choose between OpenAI, Google Gemini, or Mistral AI in the sidebar.
2. **Project Details**: Enter your project title and description.
3. **Requirements Collection**: Answer questions about your project requirements.
4. **Review Analysis**: Review the AI's understanding of your requirements.
5. **Architecture Generation**: Generate AWS cloud architecture designs.
6. **Security Assessment**: Get security recommendations and compliance information.
7. **Export Results**: Download the generated files.

## File Structure

- `main.py`: Original CLI interface for the Cloud Architecture Assistant
- `streamlit_app.py`: Streamlit web interface for the Assistant
- `requirements.txt`: Required Python packages

## Notes

- You must have at least one valid API key to use the application.
- Files are saved locally in a folder named after your project.
- The number of questions varies based on your project's complexity. 
# Cloud Architecture Design Assistant

An intelligent assistant that helps design AWS cloud architectures through natural conversation. The assistant uses various AI models (OpenAI, Google Gemini, or Mistral) to understand project requirements and generate detailed AWS architecture specifications.

## Features

- Natural conversation interface for gathering project requirements
- Support for multiple AI models (OpenAI, Google Gemini, Mistral)
- Automatic fallback between different AI providers
- Generates detailed AWS architecture specifications
- Generates structured AWS architecture JSON diagrams
- Saves conversation history and architecture prompts
- Colored console output for better readability

## Prerequisites

- Python 3.8 or higher
- API keys for at least one of the following:
  - OpenAI API key
  - Google Gemini API key
  - Mistral API key

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/cloud-architecture-assistant.git
cd cloud-architecture-assistant
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory with your API keys:
```
OPENAI_API_KEY=your_openai_api_key
GEMINI_API_KEY=your_gemini_api_key
MISTRAL_API_KEY=your_mistral_api_key
```

## Usage

### 1. Generate Architecture Design

Run the main script to start the interactive conversation:
```bash
python main.py
```

Follow the interactive prompts to provide project details. The assistant will:
- Ask relevant questions about your project requirements
- Generate a detailed AWS architecture specification
- Save the conversation and architecture details

### 2. Generate Architecture JSON

After generating the architecture design, you can create a structured JSON representation:
```bash
python generate_architecture_json.py
```

This will:
- Take your architecture prompt
- Generate a detailed AWS architecture JSON following the template structure
- Save the JSON in your project's folder

## Project Structure

- `main.py`: Main application script for interactive architecture design
- `generate_architecture_json.py`: Script for generating architecture JSON
- `templet_arch.json`: Template for architecture JSON structure
- `API Test/`: Directory containing API test scripts
  - `openai-api-test.py`: Test script for OpenAI API
  - `gemini-api-test.py`: Test script for Google Gemini API
  - `mistral-api-test.py`: Test script for Mistral API
- `requirements.txt`: List of Python dependencies

## Output Files

The assistant generates several types of files:
1. `[ProjectName]_Communication_[Timestamp].txt`: Contains the full conversation history
2. `[ProjectName]_Architecture_[Timestamp].txt`: Contains the generated AWS architecture specification
3. `[ProjectName]_Architecture_[Timestamp].json`: Contains the structured AWS architecture diagram

All files are organized in project-specific folders for better organization.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
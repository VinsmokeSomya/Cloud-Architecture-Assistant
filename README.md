# Cloud Architecture Design Assistant

An intelligent assistant that helps design AWS cloud architectures through natural conversation. The assistant uses various AI models (OpenAI, Google Gemini, or Mistral) to understand project requirements and generate detailed AWS architecture specifications. Features a user-friendly Gradio web interface for interactive sessions.

## Features

- Interactive web interface powered by Gradio
- Natural conversation interface for gathering project requirements
- Support for multiple AI models (OpenAI, Google Gemini, Mistral)
- Automatic fallback between different AI providers
- Real-time requirements analysis and confirmation
- Security assessment generation
- Architecture prompt generation
- Structured AWS architecture JSON generation
- Automatic file saving with timestamps
- Collapsible sections for better organization
- Copy-to-clipboard functionality for outputs

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

### Web Interface (Recommended)

Launch the Gradio web interface:
```bash
python gradio_interface.py
```

The interface provides:
1. Project setup with title and description
2. Interactive Q&A session
3. Real-time requirements analysis
4. Security assessment
5. Architecture generation
6. JSON architecture generation

### Command Line Interface

Alternatively, you can use the command-line interface:

1. Generate Architecture Design:
```bash
python main.py
```

2. Generate Architecture JSON:
```bash
python generate_architecture_json.py
```

## Project Structure

- `gradio_interface.py`: Main web interface using Gradio
- `main.py`: Command-line interface for architecture design
- `generate_architecture_json.py`: JSON architecture generator
- `templet_arch.json`: Template for architecture JSON structure
- `API Test/`: Directory containing API test scripts
  - `openai-api-test.py`: Test script for OpenAI API
  - `gemini-api-test.py`: Test script for Google Gemini API
  - `mistral-api-test.py`: Test script for Mistral API
- `requirements.txt`: List of Python dependencies

## Output Files

The assistant generates several types of files in project-specific folders:
1. `[ProjectName]_Conversation_[Timestamp].txt`: Full conversation history
2. `[ProjectName]_Architecture_[Timestamp].txt`: AWS architecture specification
3. `[ProjectName]_SecurityAssessment_[Timestamp].txt`: Security assessment details
4. `[ProjectName]_ArchitectureJSON_[Timestamp].json`: Structured AWS architecture

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure the API
client = MistralClient(api_key=os.getenv("MISTRAL_API_KEY"))

# List available models
print("Available Models:")
models = client.list_models()
if hasattr(models, 'data'):
    for model in models.data:  # Access the list of models
        print(f"- {model.id}")  # Print each model's ID
else:
    print("Unexpected model list format:", models)

# Initialize the model (using the best available model)
model = "open-mixtral-8x22b"  # Most powerful model for general tasks

# Test the API with a simple prompt
print("\nTesting API with a simple prompt:")
messages = [
    ChatMessage(role="user", content="Yo!, this is a test message.")
]

try:
    response = client.chat(
        model=model,
        messages=messages
    )
    print("Response:", response.choices[0].message.content)
except Exception as e:
    print(f"Error testing Mistral API: {str(e)}") 
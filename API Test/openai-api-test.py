import os
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()

# Configure OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")

def test_openai_api():
    try:
        # List available models using the new API
        print("Available Models:")
        models = openai.models.list()
        for model in models.data:
            print(f"- {model.id}")

        # Test the API with a simple prompt
        print("\nTesting API with a simple prompt...")
        response = openai.chat.completions.create(
            model="gpt-4o-2024-11-20",
            messages=[
                {"role": "user", "content": "Yo!, this is a test message."}
            ]
        )
        print("\nResponse:", response.choices[0].message.content)

    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_openai_api() 
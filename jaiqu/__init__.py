from openai import OpenAI
import os

openai_client = None

if os.getenv("OPENAI_API_KEY") is not None:
	openai_client = OpenAI()#OpenAI grabs from environment variable by default
      
def set_openai_key(openai_api_key: str):
    global openai_client
    openai_client = OpenAI(api_key=openai_api_key)
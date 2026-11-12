from dotenv import load_dotenv
import os

_ = load_dotenv("../.env")  # take environment variables from .env.

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
INWORLDTTS_API_KEY = os.getenv("INWORLDTTS_API_KEY")
INWORLDTTS_MODEL = os.getenv("INWORLDTTS_MODEL")
import os
from platformdirs import user_data_dir
from pathlib import Path
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# KEYS
OPEN_ROUTER_KEY = os.environ.get("OPEN_ROUTER_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SEARCHXNG_HOST = os.environ["SEARCHXNG_HOST"]
PINECONE_KEY = os.environ["PINECONE_KEY"]
INTROLIX_API_KEY = os.environ["INTROLIX_API_KEY"]
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]

# App Info
APP_NAME = "introlix"
APP_AUTHOR = "introlix-ai"

# JWT Config
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Database 
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/introlix.db"

# model config
HF_MODEL_URL = "https://huggingface.co/{username}/{repo_id}/resolve/{branch_name}/{model_name}?download=true"
MODEL_SAVE_DIR = Path(user_data_dir(appname=APP_NAME, appauthor=APP_AUTHOR)) / "models"

# cloud provider
CLOUD_PROVIDER = "google_ai_studio"  # or "openrouter"

# AUTO model
if CLOUD_PROVIDER == "openrouter":
    AUTO_MODEL = "deepseek/deepseek-v4-flash:free"
elif CLOUD_PROVIDER == "google_ai_studio":
    AUTO_MODEL = "gemini-3.1-flash-lite"

# Supported LLMs
SUPPORTED_LLMs = [
    {"name": "Gemini 3.5 Flash", "value": "gemini-3.5-flash", "provider": "google_ai_studio"},
    {"name": "DeepSeek V4 Flash", "value": "deepseek/deepseek-v4-flash:free", "provider": "openrouter"},
    {"name": "Gemini 3.1 Flash Lite", "value": "gemini-3.1-flash-lite", "provider": "google_ai_studio"},
    {"name": "Gemini 3.1 Pro Preview", "value": "gemini-3.1-pro-preview", "provider": "google_ai_studio"},
    {"name": "Gemini 3.1 Flash Lite Preview", "value": "gemini-3.1-flash-lite-preview", "provider": "google_ai_studio"},
    {"name": "Gemini 3 Flash Preview", "value": "gemini-3-flash-preview", "provider": "google_ai_studio"},
]

# Some settings for the app
MIN_RELEVANCE_SCORE = 0.40
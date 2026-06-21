import os
import psutil
from platformdirs import user_data_dir
from pathlib import Path
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# KEYS
OPEN_ROUTER_KEY = os.environ.get("OPEN_ROUTER_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SEARCHXNG_HOST = os.environ.get("SEARCHXNG_HOST", "")
INTROLIX_API_KEY = os.environ.get("INTROLIX_API_KEY", "local_api_key123")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "local_api_key123")

# App Info
APP_NAME = "introlix"
APP_AUTHOR = "introlix-ai"
APP_PATH = Path(user_data_dir(appname=APP_NAME, appauthor=APP_AUTHOR))

# JWT Config
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Database 
DATA_DIR = APP_PATH / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/introlix.db"

CHROMA_DB_DIR = DATA_DIR / "chroma_db"
CHROMA_DB_DIR.mkdir(exist_ok=True)

# model config
HF_MODEL_URL = "https://huggingface.co/{username}/{repo_id}/resolve/{branch_name}/{model_name}?download=true"
MODEL_SAVE_DIR = APP_PATH / "models"

# cloud provider
CLOUD_PROVIDER = "google_ai_studio"  # or "openrouter"

# Supported LLMs
SUPPORTED_LLMs = [
    {"name": "Gemini 3.5 Flash", "value": "gemini-3.5-flash", "provider": "google_ai_studio"},
    {"name": "DeepSeek V4 Flash", "value": "deepseek/deepseek-v4-flash:free", "provider": "openrouter"},
    {"name": "Gemini 3.1 Flash Lite", "value": "gemini-3.1-flash-lite", "provider": "google_ai_studio"},
    {"name": "Gemini 3.1 Pro Preview", "value": "gemini-3.1-pro-preview", "provider": "google_ai_studio"},
    {"name": "Gemini 3.1 Flash Lite Preview", "value": "gemini-3.1-flash-lite-preview", "provider": "google_ai_studio"},
    {"name": "Gemini 3 Flash Preview", "value": "gemini-3-flash-preview", "provider": "google_ai_studio"},
]

# add local models to supported list
for model_path in MODEL_SAVE_DIR.glob("*.gguf"):
    SUPPORTED_LLMs.append(
        {"name": model_path.stem, "value": str(model_path.stem) + ".gguf", "provider": "local"} # only gguf is supported till now
    )

# AUTO 
if SUPPORTED_LLMs and "local" in [model["provider"] for model in SUPPORTED_LLMs]:
    AUTO_MODEL = [model for model in SUPPORTED_LLMs if model["provider"] == "local"][0]["value"]
elif CLOUD_PROVIDER == "openrouter" and OPEN_ROUTER_KEY:
    AUTO_MODEL = "deepseek/deepseek-v4-flash:free"
elif CLOUD_PROVIDER == "google_ai_studio" and GEMINI_API_KEY:
    AUTO_MODEL = "gemini-3.1-flash-lite"

# Some settings for the app
MIN_RELEVANCE_SCORE = 0.40
CHUNK_SIZE = 400
CHUNK_OVERLAP_SIZE=30

# llama-cpp config
LLAMA_CPP_VERSION = "b9700"
CUDA_VERSION = {
    12: 12.4,
    13: 13.3
}
LLAMA_CPP_PATH = APP_PATH / f"llama-{LLAMA_CPP_VERSION}"
LLAMA_SERVER_PATH = os.path.join(LLAMA_CPP_PATH, "llama-server")
LLAMA_SERVER_PORT = 8044
LLAMA_CPP_CTX = 8192
LLAMA_CPP_N_GPU_LAYERS = int(os.environ.get("LLAMA_CPP_N_GPU_LAYERS", "99"))
PHYSICAL_CORES = psutil.cpu_count(logical=False)
"""Configuration settings for Senior AI Data Analyst Single-Agent System."""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

def get_api_key() -> str:
    """Retrieve Gemini API key with validation."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "Gemini API key is not configured.\n"
            "Please provide your API key in the web interface or configure GEMINI_API_KEY in .env."
        )
    return api_key

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_FILE_SIZE_BYTES = 16 * 1024 * 1024  # 16 MB limit

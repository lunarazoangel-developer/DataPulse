import os
from pathlib import Path

from dotenv import load_dotenv


_BACKEND_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _BACKEND_ROOT / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)


DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
DEEPSEEK_API_URL: str = (
    os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions").strip()
    or "https://api.deepseek.com/v1/chat/completions"
)

try:
    DEEPSEEK_TIMEOUT: int = int(os.getenv("DEEPSEEK_TIMEOUT", "60"))
except ValueError:
    DEEPSEEK_TIMEOUT = 60


def is_ai_enabled() -> bool:
    return bool(DEEPSEEK_API_KEY)

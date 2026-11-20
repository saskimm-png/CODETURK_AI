from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_url: str
    app_password: str
    session_secret: str
    groq_api_key: str
    zai_api_key: str
    openrouter_api_key: str
    groq_base_url: str
    zai_base_url: str
    openrouter_base_url: str
    chat_model: str
    groq_analyst_model: str
    zai_analyst_model: str
    final_code_model: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "CODETURK"),
        app_url=os.getenv("APP_URL", "http://localhost:8000").rstrip("/"),
        app_password=os.getenv("APP_PASSWORD", ""),
        session_secret=os.getenv("SESSION_SECRET") or secrets.token_urlsafe(48),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        zai_api_key=os.getenv("ZAI_API_KEY", "").strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        groq_base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
        zai_base_url=os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4").rstrip("/"),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        chat_model=os.getenv("CHAT_MODEL", "openai/gpt-oss-120b"),
        groq_analyst_model=os.getenv("GROQ_ANALYST_MODEL", "qwen/qwen3.8-27b"),
        zai_analyst_model=os.getenv("ZAI_ANALYST_MODEL", "glm-4.7-flash"),
        final_code_model=os.getenv("FINAL_CODE_MODEL", "cohere/north-mini-code:free"),
    )

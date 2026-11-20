from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai_engine import ProviderError, generate_reply
from app.config import get_settings
from app.schemas import ChatRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("codeturk")
settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="CODETURK API", version="1.1.0",
              docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"),
          name="static")

chat_attempts: dict[str, deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def allow(key: str, limit: int = 30, window: int = 60) -> bool:
    now = time.monotonic()
    queue = chat_attempts[key]

    while queue and now - queue[0] > window:
        queue.popleft()

    if len(queue) >= limit:
        return False

    queue.append(now)
    return True


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/status")
async def status():
    return {
        "app": settings.app_name,
        "providers": [
            {
                "id": "groq_chat",
                "name": "GPT-OSS 120B",
                "model": settings.chat_model,
                "configured": bool(settings.groq_api_key)
            },
            {
                "id": "groq_analyst",
                "name": "Qwen3.8-27B",
                "model": settings.groq_analyst_model,
                "configured": bool(settings.groq_api_key)
            },
            {
                "id": "zai_analyst",
                "name": "GLM-4.7-Flash",
                "model": settings.zai_analyst_model,
                "configured": bool(settings.zai_api_key)
            },
            {
                "id": "openrouter_final",
                "name": "North Mini Code",
                "model": settings.final_code_model,
                "configured": bool(settings.openrouter_api_key)
            }
        ]
    }


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    if not allow(client_key(request)):
        raise HTTPException(
            status_code=429,
            detail="Dakikadaki istek sınırına ulaştın. Biraz sonra tekrar dene."
        )

    try:
        return await generate_reply(
            settings,
            payload.message,
            payload.history,
            payload.mode
        )

    except ProviderError as exc:
        logger.warning("Provider unavailable: %s", exc.provider)
        raise HTTPException(
            status_code=502,
            detail="Bir AI sağlayıcısı yanıt veremedi. API anahtarlarını ve kotanı kontrol et."
        ) from exc

    except Exception as exc:
        logger.exception("Unexpected chat error")
        raise HTTPException(
            status_code=500,
            detail="Beklenmeyen bir sunucu hatası oluştu."
        ) from exc

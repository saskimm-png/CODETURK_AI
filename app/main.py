from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.ai_engine import ProviderError, generate_reply
from app.config import get_settings
from app.schemas import ChatRequest, LoginRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("codeturk")
settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
serializer = URLSafeTimedSerializer(settings.session_secret, salt="codeturk-session-v1")
COOKIE = "codeturk_session"
SESSION_TTL = 12 * 60 * 60
app = FastAPI(title="CODETURK API", version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
login_attempts: dict[str, deque[float]] = defaultdict(deque)
chat_attempts: dict[str, deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def allow(bucket: dict[str, deque[float]], key: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    queue = bucket[key]
    while queue and now - queue[0] > window:
        queue.popleft()
    if len(queue) >= limit:
        return False
    queue.append(now)
    return True


def authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        return serializer.loads(token, max_age=SESSION_TTL).get("authenticated") is True
    except (BadSignature, TypeError, AttributeError):
        return False


async def require_auth(request: Request) -> None:
    if not authenticated(request):
        raise HTTPException(status_code=401, detail="Oturum açman gerekiyor.")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    key = client_key(request)
    if not allow(login_attempts, key, 8, 300):
        raise HTTPException(status_code=429, detail="Çok fazla deneme. Daha sonra tekrar dene.")
    if not settings.app_password:
        raise HTTPException(status_code=503, detail="Sunucuda APP_PASSWORD ayarlanmamış.")
    supplied = hashlib.sha256(payload.password.encode()).digest()
    expected = hashlib.sha256(settings.app_password.encode()).digest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Parola yanlış.")
    token = serializer.dumps({"authenticated": True})
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    secure = request.url.scheme == "https" or forwarded == "https"
    response.set_cookie(
        COOKIE, token, max_age=SESSION_TTL, httponly=True, secure=secure,
        samesite="strict", path="/",
    )
    return {"status": "ok"}


@app.post("/api/auth/logout", dependencies=[Depends(require_auth)])
async def logout(request: Request, response: Response):
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    secure = request.url.scheme == "https" or forwarded == "https"
    response.delete_cookie(COOKIE, httponly=True, secure=secure, samesite="strict", path="/")
    return {"status": "ok"}


@app.get("/api/status", dependencies=[Depends(require_auth)])
async def status():
    return {"app": settings.app_name, "providers": [
        {"id": "groq_chat", "name": "GPT-OSS 120B", "model": settings.chat_model,
         "configured": bool(settings.groq_api_key)},
        {"id": "groq_analyst", "name": "Qwen3.8-27B", "model": settings.groq_analyst_model,
         "configured": bool(settings.groq_api_key)},
        {"id": "zai_analyst", "name": "GLM-4.7-Flash", "model": settings.zai_analyst_model,
         "configured": bool(settings.zai_api_key)},
        {"id": "openrouter_final", "name": "North Mini Code", "model": settings.final_code_model,
         "configured": bool(settings.openrouter_api_key)},
    ]}


@app.post("/api/chat", dependencies=[Depends(require_auth)])
async def chat(payload: ChatRequest, request: Request):
    if not allow(chat_attempts, client_key(request), 30, 60):
        raise HTTPException(status_code=429, detail="İstek sınırına ulaştın. Biraz sonra tekrar dene.")
    try:
        return await generate_reply(settings, payload.message, payload.history, payload.mode)
    except ProviderError as exc:
        logger.warning("Provider unavailable: %s", exc.provider)
        raise HTTPException(
            status_code=502,
            detail="Bir AI sağlayıcısı yanıt veremedi. API anahtarlarını, model erişimini ve kotanı kontrol et.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected chat error")
        raise HTTPException(status_code=500, detail="Beklenmeyen bir sunucu hatası oluştu.") from exc

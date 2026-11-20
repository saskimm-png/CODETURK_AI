from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from app.config import Settings
from app.schemas import HistoryMessage

logger = logging.getLogger("codeturk.ai")


class ProviderError(RuntimeError):
    def __init__(self, provider: str, status_code: int | None = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} yanıt veremedi.")


CODE_HINTS = re.compile(
    r"\b(kod|kodla|programla|programlama|yazılım|debug|html|css|javascript|"
    r"typescript|python|java|kotlin|php|sql|api|backend|frontend|react|node|"
    r"fastapi|github|fonksiyon|class|function|script|uygulama yap|site yap|"
    r"web sitesi|apk|algoritma|terminal|komut satırı)\b",
    re.IGNORECASE,
)


def detect_mode(message: str) -> str:
    return "code" if CODE_HINTS.search(message) else "chat"


def _read_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("Model boş yanıt döndürdü.")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts = [x.get("text", "") for x in content if isinstance(x, dict)]
        result = "\n".join(x for x in parts if isinstance(x, str)).strip()
        if result:
            return result
    raise ValueError("Model yanıtı okunamadı.")


async def completion(
    client: httpx.AsyncClient, provider: str, base_url: str, api_key: str,
    model: str, messages: list[dict[str, str]], max_tokens: int,
) -> str:
    if not api_key:
        raise ProviderError(provider)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "OpenRouter":
        headers.update({"HTTP-Referer": "https://codeturk.app", "X-Title": "CODETURK"})
    try:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
        )
        if response.status_code >= 400:
            logger.warning("%s returned HTTP %s", provider, response.status_code)
            raise ProviderError(provider, response.status_code)
        return _read_content(response.json())
    except httpx.TimeoutException as exc:
        raise ProviderError(provider, 504) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(provider, 502) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise ProviderError(provider, 502) from exc


def history_payload(history: list[HistoryMessage]) -> list[dict[str, str]]:
    return [{"role": item.role, "content": item.content[:7000]} for item in history[-12:]]


async def generate_reply(
    settings: Settings, message: str, history: list[HistoryMessage], requested_mode: str
) -> dict[str, Any]:
    mode = detect_mode(message) if requested_mode == "auto" else requested_mode
    timeout = httpx.Timeout(100.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=6)) as client:
        if mode == "chat":
            if not settings.groq_api_key:
                raise ProviderError("Groq GPT-OSS 120B")
            messages = [{
                "role": "system",
                "content": (
                    "Sen CODETURK'sün. Türkçe, açık ve yardımsever cevap ver. "
                    "Bilmediğin bilgiyi uydurma. Kullanıcı kod istemedikçe kod üretme."
                ),
            }]
            messages.extend(history_payload(history))
            messages.append({"role": "user", "content": message})
            started = time.monotonic()
            reply = await completion(
                client, "Groq GPT-OSS 120B", settings.groq_base_url,
                settings.groq_api_key, settings.chat_model, messages, 3000,
            )
            return {
                "reply": reply, "mode": "chat", "degraded": False,
                "pipeline": [{
                    "name": "Genel sohbet", "model": settings.chat_model,
                    "status": "ok", "duration": str(round(time.monotonic() - started, 1)),
                }],
            }

        context = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in history_payload(history)
        )[-10000:]
        task = f"ÖNCEKİ BAĞLAM:\n{context or '(yok)'}\n\nYENİ İSTEK:\n{message}"
        prompts = [
            (
                "Groq Qwen", settings.groq_base_url, settings.groq_api_key,
                settings.groq_analyst_model,
                "Bağımsız kıdemli yazılım mimarısısın. İsteği analiz et; gereksinim, "
                "mimari, dosya etkileri, kenar durumları, güvenlik ve testleri içeren "
                "somut bir rapor ver. Gizli düşünce zinciri verme.",
            ),
            (
                "Z.ai GLM", settings.zai_base_url, settings.zai_api_key,
                settings.zai_analyst_model,
                "İkinci bağımsız yazılım uzmanısın. İsteği ayrı değerlendir; alternatif "
                "yaklaşım, olası hata, uyumluluk, güvenlik ve test önerilerini yaz. "
                "Başka modelin raporunu görmedin. Gizli düşünce zinciri verme.",
            ),
        ]

        async def analyst(item):
            label, base, key, model, system = item
            if not key:
                return None, {"name": label, "model": model, "status": "missing_key", "duration": "0"}
            started = time.monotonic()
            try:
                result = await completion(
                    client, label, base, key, model,
                    [{"role": "system", "content": system}, {"role": "user", "content": task}],
                    2200,
                )
                return result, {
                    "name": label, "model": model, "status": "ok",
                    "duration": str(round(time.monotonic() - started, 1)),
                }
            except ProviderError:
                return None, {"name": label, "model": model, "status": "error", "duration": "0"}

        (qwen, qwen_state), (glm, glm_state) = await asyncio.gather(
            analyst(prompts[0]), analyst(prompts[1])
        )
        reports = (
            "QWEN BAĞIMSIZ ANALİZİ:\n" + (qwen or "Bu model yanıt veremedi.")
            + "\n\nGLM BAĞIMSIZ ANALİZİ:\n" + (glm or "Bu model yanıt veremedi.")
        )
        system = (
            "CODETURK'ün son kod üreticisisin. İki bağımsız raporu karşılaştır; "
            "doğru noktaları birleştir, hatalı önerileri ele. İstenen işi tamamla. "
            "Kod gerekiyorsa çalıştırılabilir kodu ve dosya yollarını ver. Gereksiz "
            "dosyaları değiştirme, güvenliği koru. Türkçe yanıt ver. Gizli düşünce "
            "zinciri yerine kısa karar özeti ve nihai sonucu sun."
        )
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": task + "\n\n" + reports}]
        pipeline = [qwen_state, glm_state]
        degraded = qwen_state["status"] != "ok" or glm_state["status"] != "ok"

        if settings.openrouter_api_key:
            started = time.monotonic()
            try:
                reply = await completion(
                    client, "OpenRouter", settings.openrouter_base_url,
                    settings.openrouter_api_key, settings.final_code_model, messages, 7000,
                )
                pipeline.append({
                    "name": "Son kod üretimi", "model": settings.final_code_model,
                    "status": "ok", "duration": str(round(time.monotonic() - started, 1)),
                })
                return {"reply": reply, "mode": "code", "pipeline": pipeline, "degraded": degraded}
            except ProviderError:
                degraded = True
                pipeline.append({
                    "name": "OpenRouter North Mini Code", "model": settings.final_code_model,
                    "status": "error", "duration": "0",
                })

        if settings.groq_api_key:
            started = time.monotonic()
            reply = await completion(
                client, "Groq fallback", settings.groq_base_url,
                settings.groq_api_key, settings.chat_model,
                [{"role": "system", "content": system + " North modeli kullanılamıyor; "
                  "iki raporu sentezleyerek son yanıtı sen üret."}, messages[-1]], 6500,
            )
            pipeline.append({
                "name": "Yedek son yanıt", "model": settings.chat_model,
                "status": "fallback", "duration": str(round(time.monotonic() - started, 1)),
            })
            return {"reply": reply, "mode": "code", "pipeline": pipeline, "degraded": True}
        raise ProviderError("Son kod üretim modeli")

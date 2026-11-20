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
    def __init__(
        self,
        provider: str,
        status_code: int | None = None
    ):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} yanıt veremedi.")


# Kod isteğini otomatik algılamak için anahtar kelimeler
CODE_HINTS = re.compile(
    r"\b("
    r"kod|kodla|programla|programlama|yazılım|debug|"
    r"html|css|javascript|typescript|python|java|kotlin|php|sql|"
    r"api|backend|frontend|react|node|fastapi|github|"
    r"fonksiyon|class|function|script|uygulama yap|site yap|"
    r"web sitesi|apk|algoritma|terminal|komut satırı|"
    r"dosya oluştur|dosyayı düzenle|hata düzelt"
    r")\b",
    re.IGNORECASE,
)


CHAT_SYSTEM_PROMPT = """
Sen CODETURK adlı çok modelli yapay zekâ asistanısın.

KONUŞMA KURALLARI:
- Kullanıcıyla Türkçe konuş.
- Açık, doğal ve yardımsever ol.
- Bilmediğin bilgileri uydurma.
- Kullanıcı istemedikçe gereksiz kod üretme.
- Kendini asla GPT-4, ChatGPT veya OpenAI modeli olarak tanıtma.
- Sen CODETURK sisteminin sohbet asistanısın.

CODETURK MODEL MİMARİSİ:
1. Normal sohbetlerde Groq üzerinden GPT-OSS 120B kullanılır.
2. Kod görevlerinde Qwen 3.8 27B bağımsız analiz yapar.
3. Aynı kod görevinde GLM 4.7 Flash ikinci bağımsız analizi yapar.
4. North Mini Code iki analizi değerlendirerek nihai kodu üretir.
5. North kullanılamazsa GPT-OSS yedek olarak kullanılabilir.

Kullanıcı hangi modellerin kullanıldığını sorarsa bu mimariyi açıkla.
Ancak bir modelin API anahtarı eksikse veya model çalışmıyorsa
o modelin o anda aktif olduğunu iddia etme.

Önemli: Bu açıklama sistem mimarisidir. Gerçek çalışma durumunu
sana verilen işlem sonuçları belirler.
""".strip()


QWEN_SYSTEM_PROMPT = """
Sen CODETURK sisteminin bağımsız kıdemli yazılım analistisin.

Görevin:
- Kullanıcının isteğini teknik açıdan analiz etmek.
- Gereksinimleri belirlemek.
- Uygun mimariyi önermek.
- Etkilenecek dosyaları belirtmek.
- Güvenlik açıklarını ve kenar durumlarını incelemek.
- Hatalı veya eksik noktaları tespit etmek.
- Test önerileri sunmak.

Türkçe cevap ver.
Somut ve uygulanabilir bir analiz hazırla.
Gizli düşünce zincirini açıklama.
""".strip()


GLM_SYSTEM_PROMPT = """
Sen CODETURK sisteminin ikinci bağımsız yazılım denetçisisin.

Qwen'in analizini görmeden bağımsız değerlendirme yap.

Görevin:
- İsteği farklı bir açıdan incelemek.
- Alternatif çözümler bulmak.
- Uyumluluk sorunlarını belirlemek.
- Güvenlik ve performansı değerlendirmek.
- Muhtemel hataları tespit etmek.
- Test ve iyileştirme önerileri sunmak.

Türkçe cevap ver.
Gizli düşünce zincirini açıklama.
""".strip()


FINAL_SYSTEM_PROMPT = """
Sen CODETURK'ün son kod üretim ve karar modelisin.

Önüne iki bağımsız yapay zekâ analiz raporu gelecek.

Görevin:
1. İki raporu karşılaştır.
2. Doğru ve yararlı önerileri birleştir.
3. Çelişkili veya hatalı önerileri ele.
4. Kullanıcının asıl isteğini tamamla.
5. Kod gerekiyorsa eksiksiz ve çalıştırılabilir kod üret.
6. Dosya yollarını açıkça belirt.
7. Kullanıcı istemedikçe gereksiz dosyaları değiştirme.
8. Güvenlik ve mevcut proje uyumluluğunu koru.

Türkçe yanıt ver.
Gerekirse kısa bir karar özeti sun.
Gizli düşünce zincirini açıklama.

Kendini ChatGPT veya GPT-4 olarak tanıtma.
Sen CODETURK'ün son kod üretim modelisin.
""".strip()


def detect_mode(message: str) -> str:
    """İsteğin sohbet mi kod mu olduğunu belirler."""
    return "code" if CODE_HINTS.search(message) else "chat"


def _read_content(payload: dict[str, Any]) -> str:
    """OpenAI uyumlu API yanıtından metni alır."""
    choices = payload.get("choices") or []

    if not choices:
        raise ValueError("Model boş yanıt döndürdü.")

    content = (choices[0].get("message") or {}).get("content")

    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict)
        ]

        result = "\n".join(
            part for part in parts
            if isinstance(part, str)
        ).strip()

        if result:
            return result

    raise ValueError("Model yanıtı okunamadı.")


async def completion(
    client: httpx.AsyncClient,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 3000,
) -> str:
    """Bir model sağlayıcısından yanıt alır."""

    if not api_key:
        raise ProviderError(provider, 401)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if provider == "OpenRouter":
        headers.update({
            "HTTP-Referer": "https://codeturk.app",
            "X-Title": "CODETURK",
        })

    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
            },
        )

        if response.status_code >= 400:
            logger.warning(
                "%s API hatası: HTTP %s",
                provider,
                response.status_code,
            )
            raise ProviderError(provider, response.status_code)

        return _read_content(response.json())

    except ProviderError:
        raise

    except httpx.TimeoutException as exc:
        logger.warning("%s zaman aşımına uğradı.", provider)
        raise ProviderError(provider, 504) from exc

    except httpx.HTTPError as exc:
        logger.warning("%s bağlantı hatası.", provider)
        raise ProviderError(provider, 502) from exc

    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("%s yanıtı okunamadı.", provider)
        raise ProviderError(provider, 502) from exc


def history_payload(
    history: list[HistoryMessage]
) -> list[dict[str, str]]:
    """Sohbet geçmişini API formatına dönüştürür."""

    return [
        {
            "role": item.role,
            "content": item.content[:7000],
        }
        for item in history[-12:]
    ]


async def run_chat(
    client: httpx.AsyncClient,
    settings: Settings,
    message: str,
    history: list[HistoryMessage],
) -> dict[str, Any]:
    """Normal sohbeti GPT-OSS 120B ile yürütür."""

    started = time.monotonic()

    messages = [
        {
            "role": "system",
            "content": CHAT_SYSTEM_PROMPT,
        }
    ]

    messages.extend(history_payload(history))

    messages.append({
        "role": "user",
        "content": message,
    })

    reply = await completion(
        client=client,
        provider="Groq GPT-OSS 120B",
        base_url=settings.groq_base_url,
        api_key=settings.groq_api_key,
        model=settings.chat_model,
        messages=messages,
        max_tokens=3000,
    )

    return {
        "reply": reply,
        "mode": "chat",
        "degraded": False,
        "pipeline": [
            {
                "name": "Genel sohbet",
                "model": settings.chat_model,
                "status": "ok",
                "duration": str(
                    round(time.monotonic() - started, 1)
                ),
            }
        ],
    }


async def run_analyst(
    client: httpx.AsyncClient,
    name: str,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    task: str,
) -> tuple[str | None, dict[str, Any]]:
    """Qwen veya GLM analizini çalıştırır."""

    started = time.monotonic()

    if not api_key:
        return None, {
            "name": name,
            "model": model,
            "status": "missing_key",
            "duration": "0",
        }

    try:
        result = await completion(
            client=client,
            provider=name,
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": task,
                },
            ],
            max_tokens=2500,
        )

        return result, {
            "name": name,
            "model": model,
            "status": "ok",
            "duration": str(
                round(time.monotonic() - started, 1)
            ),
        }

    except ProviderError as exc:
        logger.warning("%s analiz yapamadı: %s", name, exc)

        return None, {
            "name": name,
            "model": model,
            "status": "error",
            "duration": str(
                round(time.monotonic() - started, 1)
            ),
        }


async def run_code(
    client: httpx.AsyncClient,
    settings: Settings,
    message: str,
    history: list[HistoryMessage],
) -> dict[str, Any]:
    """İki analiz modelini ve son kod modelini birlikte çalıştırır."""

    context = "\n".join(
        f"{item['role'].upper()}: {item['content']}"
        for item in history_payload(history)
    )[-10000:]

    task = (
        f"ÖNCEKİ SOHBET BAĞLAMI:\n{context or '(önceki bağlam yok)'}"
        f"\n\nKULLANICININ YENİ İSTEĞİ:\n{message}"
    )

    # İki bağımsız model aynı anda çalışır.
    qwen_result, glm_result = await asyncio.gather(
        run_analyst(
            client,
            "Groq Qwen",
            settings.groq_base_url,
            settings.groq_api_key,
            settings.groq_analyst_model,
            QWEN_SYSTEM_PROMPT,
            task,
        ),
        run_analyst(
            client,
            "Z.ai GLM",
            settings.zai_base_url,
            settings.zai_api_key,
            settings.zai_analyst_model,
            GLM_SYSTEM_PROMPT,
            task,
        ),
    )

    qwen_report, qwen_status = qwen_result
    glm_report, glm_status = glm_result

    reports = (
        "QWEN ANALİZ RAPORU:\n"
        + (qwen_report or "Qwen bu isteği analiz edemedi.")
        + "\n\nGLM ANALİZ RAPORU:\n"
        + (glm_report or "GLM bu isteği analiz edemedi.")
    )

    messages = [
        {
            "role": "system",
            "content": FINAL_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": task + "\n\n" + reports,
        },
    ]

    pipeline = [
        qwen_status,
        glm_status,
    ]

    degraded = (
        qwen_status["status"] != "ok"
        or glm_status["status"] != "ok"
    )

    # Öncelik North Mini Code modelinde.
    if settings.openrouter_api_key:
        started = time.monotonic()

        try:
            reply = await completion(
                client=client,
                provider="OpenRouter",
                base_url=settings.openrouter_base_url,
                api_key=settings.openrouter_api_key,
                model=settings.final_code_model,
                messages=messages,
                max_tokens=7000,
            )

            pipeline.append({
                "name": "Son kod üretimi",
                "model": settings.final_code_model,
                "status": "ok",
                "duration": str(
                    round(time.monotonic() - started, 1)
                ),
            })

            return {
                "reply": reply,
                "mode": "code",
                "pipeline": pipeline,
                "degraded": degraded,
            }

        except ProviderError:
            degraded = True

            pipeline.append({
                "name": "North Mini Code",
                "model": settings.final_code_model,
                "status": "error",
                "duration": str(
                    round(time.monotonic() - started, 1)
                ),
            })

    else:
        degraded = True

        pipeline.append({
            "name": "North Mini Code",
            "model": settings.final_code_model,
            "status": "missing_key",
            "duration": "0",
        })

    # North çalışmazsa GPT-OSS iki analizi değerlendirir.
    if settings.groq_api_key:
        started = time.monotonic()

        fallback_messages = [
            {
                "role": "system",
                "content": (
                    FINAL_SYSTEM_PROMPT
                    + "\nNorth Mini Code kullanılamıyor. "
                    "İki analiz raporunu değerlendir ve "
                    "nihai cevabı sen üret."
                ),
            },
            messages[-1],
        ]

        reply = await completion(
            client=client,
            provider="Groq GPT-OSS yedek",
            base_url=settings.groq_base_url,
            api_key=settings.groq_api_key,
            model=settings.chat_model,
            messages=fallback_messages,
            max_tokens=6500,
        )

        pipeline.append({
            "name": "GPT-OSS yedek üretim",
            "model": settings.chat_model,
            "status": "fallback",
            "duration": str(
                round(time.monotonic() - started, 1)
            ),
        })

        return {
            "reply": reply,
            "mode": "code",
            "pipeline": pipeline,
            "degraded": True,
        }

    raise ProviderError("Son kod üretim modeli")


async def generate_reply(
    settings: Settings,
    message: str,
    history: list[HistoryMessage],
    requested_mode: str,
) -> dict[str, Any]:
    """Uygulamanın ana giriş noktası."""

    mode = (
        detect_mode(message)
        if requested_mode == "auto"
        else requested_mode
    )

    timeout = httpx.Timeout(
        120.0,
        connect=20.0,
    )

    limits = httpx.Limits(
        max_connections=6,
        max_keepalive_connections=3,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
    ) as client:

        if mode == "chat":
            return await run_chat(
                client,
                settings,
                message,
                history,
            )

        return await run_code(
            client,
            settings,
            message,
            history,
        )

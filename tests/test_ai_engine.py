from app.ai_engine import detect_mode
from app.schemas import ChatRequest


def test_normal_chat():
    assert detect_mode("Merhaba, bugün nasılsın?") == "chat"


def test_python_api_request():
    assert detect_mode("Python ile bir API yaz") == "code"


def test_website_request():
    assert detect_mode("Profesyonel bir web sitesi yap") == "code"


def test_case_insensitive():
    assert detect_mode("HTML ve CSS düzenle") == "code"


def test_chat_request_accepts_text_file():
    payload = ChatRequest(
        message="Bu dosyayı incele",
        attachments=[{"name": "index.html", "content": "<h1>Merhaba</h1>"}],
    )
    assert payload.attachments[0].name == "index.html"


def test_chat_request_rejects_env_file():
    try:
        ChatRequest(message="Bunu incele", attachments=[{"name": ".env", "content": "SECRET=x"}])
    except Exception:
        return
    raise AssertionError(".env dosyası kabul edilmemeliydi")

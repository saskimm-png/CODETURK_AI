from app.ai_engine import detect_mode


def test_normal_chat():
    assert detect_mode("Merhaba, bugün nasılsın?") == "chat"


def test_python_api_request():
    assert detect_mode("Python ile bir API yaz") == "code"


def test_website_request():
    assert detect_mode("Profesyonel bir web sitesi yap") == "code"


def test_case_insensitive():
    assert detect_mode("HTML ve CSS düzenle") == "code"

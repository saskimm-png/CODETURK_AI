# CODETURK

CODETURK, Türkçe bir yapay zekâ sohbet ve yazılım geliştirme çalışma alanıdır. Genel sohbeti tek modelle, kod isteklerini dört modelin görev paylaşımıyla yürütür.

## Model ekibi

| Rol | Sağlayıcı / model | Görev |
| --- | --- | --- |
| Genel sohbet | Groq – GPT-OSS 120B | Kod dışı sorular |
| Kod analisti 1 | Groq – Qwen3.8-27B | Bağımsız teknik analiz |
| Kod analisti 2 | Z.ai – GLM-4.7-Flash | İkinci bağımsız analiz |
| Son kod üreticisi | OpenRouter – North Mini Code (free) | İki raporu sentezleyip nihai yanıt |

Kod modunda iki analist paralel çalışır. Son model iki raporu birleştirir. North erişilemezse ayarlı Groq modeli yedek yanıt verebilir. Sağlayıcıların model adları ve ücretsiz kullanım limitleri zamanla değişebilir; `.env` içindeki model değerlerini hesabındaki güncel model kimlikleriyle doğrula.

## Güvenlik

- API anahtarları yalnızca sunucuda ortam değişkeni olarak tutulur; tarayıcıya gönderilmez.
- Gerçek `.env` dosyası Git'e eklenmez.
- Parola korumalı oturum, HttpOnly çerez ve temel istek sınırlaması vardır.
- Sohbet geçmişi tarayıcı belleğinde tutulur; sunucuda kalıcı sohbet veritabanı yoktur.
- Bu ilk sürümde hız sınırları uygulama belleğindedir. Birden fazla sunucu örneğinde Redis gibi ortak depolama kullanın.

## Yerel kurulum

Python 3.11+ önerilir.

1. Depoyu indir ve proje klasöründe terminal aç.
2. Sanal ortam oluştur: `python -m venv .venv`
3. Etkinleştir:
   - Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
   - macOS/Linux: `source .venv/bin/activate`
4. Bağımlılıkları kur: `pip install -r requirements.txt`
5. `.env.example` dosyasını `.env` olarak kopyala.
6. `.env` içine özel `APP_PASSWORD`, rastgele `SESSION_SECRET` ve üç API anahtarını gir.
7. Başlat: `uvicorn app.main:app --reload`
8. `http://localhost:8000` adresini aç.

Rastgele oturum anahtarı üretmek için: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

## Render

1. Render'da **New + → Blueprint** seç ve GitHub deposunu bağla.
2. `APP_PASSWORD` için uzun ve özel bir parola belirle.
3. `GROQ_API_KEY`, `ZAI_API_KEY`, `OPENROUTER_API_KEY` gizli değerlerini Render Environment alanına gir.
4. `SESSION_SECRET` Render tarafından oluşturulur.
5. `APP_URL` değerine dağıtılan HTTPS adresini gir.
6. Dağıtım sonrası `/api/health` kontrolü yap.

## API anahtarı panelleri

- Groq: https://console.groq.com/keys
- Z.ai: https://z.ai/manage-apikey/apikey-list
- OpenRouter: https://openrouter.ai/settings/keys

Ücretsiz model kotası veya API erişimi garanti edilmez. Anahtarları GitHub'a veya istemci tarafındaki JavaScript dosyalarına yazma.

## Proje yapısı

```text
CODETURK/
├── app/
│   ├── ai_engine.py
│   ├── config.py
│   ├── main.py
│   ├── schemas.py
│   └── static/
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
├── tests/test_ai_engine.py
├── .env.example
├── .gitignore
├── render.yaml
├── requirements.txt
└── README.md
```

# RetroChatbot

Zaman Makinesi — kendini bazen 1996'da, bazen 2030'da sanan bir sohbet botu. Gemini API ile konuşuyor, arayüz FastAPI + düz HTML/CSS/JS üzerine kurulu.

## Ne var ne yok

- **1996 modu**: GeoCities esintili, yanıp sönen başlık, "best viewed 800x600" rozetleri, dial-up modem havası. Bot kendini gerçekten o dönemde sanıyor ama güncel bir şey sorulduğunda bilgiyi doğru veriyor, sadece 90'lar üslubuyla anlatıyor.
- **2030 modu**: Neon/cyberpunk tema ve gerçek bir 3D hologram (Three.js ile, tavandan projekte edilen bir insan figürü). Bot bu modda ileri teknoloji diliyle konuşuyor.
- İki mod arasında geçiş yapan bir buton var, seçim sunucu tarafında saklanıyor (sayfa yenilense de kalıyor).
- Misafir defteri ve ziyaretçi sayacı — dönemin ruhuna uygun küçük eklentiler.
- Gemini modeli geçici olarak yoğunluk (503) verirse, otomatik olarak başka bir modele geçip tekrar deniyor.

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`.env.example` dosyasını `.env` olarak kopyala ve kendi Gemini API anahtarını gir:

```
GEMINI_API_KEY=senin-api-anahtarin
GEMINI_MODEL=gemini-3.8-flash
```

Ardından çalıştır:

```bash
uvicorn app.main:app --reload
```

`http://127.0.0.1:8000` üzerinden açılıyor.

## Testler

```bash
pytest
```

## Kullanılan teknolojiler

FastAPI, Jinja2, google-genai (Gemini API), vanilla JavaScript/CSS, Three.js (sadece 2030 modundaki hologram sahnesi için, CDN üzerinden).

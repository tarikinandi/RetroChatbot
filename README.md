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
pip install -r requirements-dev.txt
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

## Public demo (Vercel)

`api/index.py` + `vercel.json` publish a **stateless, chat-only** build on Vercel (Python serverless, Hobby plan).

Devre disi birakilanlar ve nedeni:

- **Misafir defteri, ziyaretci sayaci, `/toggle-era`**: sunucuda dosya yazmayi gerektirirler; serverless dosya sistemi kalici degil ve herkese acik bir sitede paylasilan durum istemiyoruz. Bu rotalar 404 doner.
- **Sohbet gecmisi**: sunucuda tutulmaz. Tarayici gecmisi `sessionStorage`'da saklar ve her istekte en fazla son 10 mesaji gonderir.
- **Donem (1996/2030)**: istek bazli. Sayfa `?era=2030` ile (ve cerezle) secilir, sohbet istegi `era` alanini tasir; global durum yok.

Korumalar: mesaj 1..500 karakter, en fazla 10 gecmis ogesi (rol `user`/`model`), kontrol karakterleri temizlenir (aksi halde 422); CORS yalnizca portfolyo adresi ve dev adresleri icin; Origin basligi izinli degilse 403; IP basina dakikada 5 istek ve gunluk toplam `DAILY_CAP` sinirlari (bellek ici, serverless'ta "best effort" - asil sinir Vercel Firewall kuralidir); tek model, en fazla bir yeniden deneme, toplam ~8 sn zaman asimi; hatalarda istemciye genel mesaj, loglarda yalnizca istisna sinifi adi.

Ortam degiskenleri (Vercel > Settings > Environment Variables):

| Ad | Aciklama |
|---|---|
| `GEMINI_API_KEY` | **Gizli.** Yalnizca hosting ortaminda tutulur, koda/repoya yazilmaz. Yoksa `/api/chat` 503 doner ("demo henuz hazir degil"). |
| `GEMINI_MODEL` | Kullanilacak tek model (varsayilan `gemini-3.8-flash`). |
| `DEMO_MODE` | `1` = demo davranisi. `api/index.py` bunu varsayilan olarak acar. |
| `DAILY_CAP` | Gunluk yumusak ust sinir (varsayilan 300). |
| `ALLOWED_ORIGIN` | Izinli site (varsayilan `https://portfolio-mtinandi.vercel.app`). |

Yerelde demo modunu denemek icin:

```bash
pip install -r requirements-dev.txt
set DEMO_MODE=1
uvicorn app.main:app --reload
```

`DEMO_MODE` tanimli degilse uygulama eskisi gibi (dosya tabanli, misafir defteri dahil) calisir. Testler gercek anahtar veya ag kullanmaz.

## Testler

```bash
pytest
```

## Kullanılan teknolojiler

FastAPI, Jinja2, google-genai (Gemini API), vanilla JavaScript/CSS, Three.js (sadece 2030 modundaki hologram sahnesi için, CDN üzerinden).

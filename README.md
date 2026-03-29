# MyEZ Integration Layer — Odoo + FastAPI + iOS

FastAPI backend serving as the integration layer between Odoo ERP, Firebase Realtime Database, and the MyEZ iOS client. Exposes clean REST endpoints consumed by the mobile app, manages FCM push notifications, triggers automatic rank-up alerts via Google Cloud Run, and delivers Dropbox product image links per SKU.

## Live API
https://myez-odooapi-production.up.railway.app

## Architecture
```mermaid
graph TD
    subgraph iOS["📱 iOS Client (SwiftUI)"]
        A[DealsView]
        B[Pull to Refresh]
        C[Loading / Error State]
        D[Login / Signup]
        N2[DownloadUnitSheet]
    end

    subgraph Railway["☁️ Railway (PaaS)"]
        E[FastAPI Middleware]
        F[GET /ping]
        G[GET /odoo/ping]
        H[GET /odoo/clients]
        I[GET /odoo/clients/ranking]
        J[GET /clients/owned-units/partner_id]
        K[POST /notify]
        L[POST /register-token]
        M[POST /notify/user/partner_id]
        P[GET /products]
        Q[GET /products/product_id]
        R2[GET /products/image/sku]
    end

    subgraph Odoo["🗄️ Odoo ERP"]
        N[res.partner]
        O[x_studio_rank_weight]
        PA[account.move]
        QA[x_studio_owned_weight]
    end

    subgraph CloudRun["⚡ Google Cloud Run"]
        R[odoo-sync service]
    end

    subgraph Firebase["🔥 Firebase"]
        S[Realtime Database]
        T[users/partner_id/fcmTokens]
        U[users/partner_id/typeuser]
        V[users/partner_id/owned_weight]
        W[users/partner_id/units]
        X[FCM Push Notifications]
    end

    subgraph Dropbox["📦 Dropbox"]
        DB1[MainImages folder]
        DB2[SKU/SKU-PNG subfolders]
    end

    D -->|login success| L
    A -->|REST HTTP GET| E
    B --> A
    C --> A
    N2 -->|GET /products/image/sku| R2
    E -->|XML-RPC| N
    E -->|XML-RPC| O
    E --> S
    L --> T
    M --> X
    J --> S
    R2 -->|OAuth2| DB1
    DB1 --> DB2
    Odoo -->|server action| R
    R -->|writes| S
    R -->|writes rank back| N
    R -->|rank changed| M
    X -->|APNs| iOS

    subgraph Config["🔐 Config"]
        Y[.env — credentials]
        Z[Railway env vars]
    end

    Y --> E
    Z --> E
```

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ping` | Health check — confirms API is live |
| GET | `/odoo/ping` | Odoo auth check — confirms XML-RPC connection |
| GET | `/odoo/clients` | Returns live client list from Odoo |
| GET | `/odoo/clients/ranking` | Returns clients ranked by inflatable weight owned. Null values handled as "No Rank Yet", ranked clients sorted first. |
| GET | `/clients/owned-units/{partner_id}` | Returns owned inflatable units, total weight, and rank tier for a specific customer from Firebase. |
| GET | `/products` | Returns published products from Odoo shop |
| GET | `/products/{product_id}` | Returns single product detail from Odoo |
| GET | `/products/image/{sku}` | Returns Dropbox shared folder URL for a SKU's image folder (`/MainImages (1)/{sku}/{sku}-PNG`). Auto-refreshes Dropbox OAuth2 token if expired. |
| POST | `/notify` | Sends push notification to a specific device via FCM token. Params: `token`, `title`, `body` |
| POST | `/register-token` | Registers a device FCM token in Firebase Realtime Database. Supports multiple devices per user. Params: `partner_id`, `token` |
| POST | `/notify/user/{partner_id}` | Sends push notification to all registered devices for an Odoo partner. Params: `title`, `body` |
| POST | `/odoo/check-rank-changes` | Manual bulk rank check across all partners |

## Dropbox Integration

Product images are stored in a team Dropbox account under `/MainImages (1)/{SKU}/{SKU}-PNG/`.

The `/products/image/{sku}` endpoint:
1. Authenticates via OAuth2 using a scoped Dropbox app (`Full Dropbox` access)
2. Auto-refreshes the access token using `DROPBOX_REFRESH_TOKEN` when expired
3. Creates or retrieves a shared folder link for `{SKU}-PNG`
4. Returns the public URL — iOS client appends `dl=1` for direct download or uses `dl=0` to open in browser

## Rank Tiers

| Rank | Weight Threshold |
|------|-----------------|
| Minimumweight | < 2,500 lb |
| Flyweight | < 5,000 lb |
| Bantamweight | < 7,500 lb |
| Featherweight | < 10,000 lb |
| Lightweight | < 12,500 lb |
| Welterweight | < 15,000 lb |
| Middleweight | < 17,500 lb |
| Cruiserweight | < 20,000 lb |
| Heavyweight | 20,001 lb+ |

## Firebase Structure

```
users/
  {partner_id}/
    name
    email
    owned_weight
    typeuser        ← rank tier name
    fcmTokens       ← array of FCM tokens
    units/          ← SKU: quantity dict
    last_sync
rank_cache/
  {partner_id}: rank_name
```

## Stack

- **FastAPI** — REST API middleware layer
- **Odoo XML-RPC** — ERP data source (res.partner, account.move)
- **Railway** — PaaS cloud deployment
- **Firebase Realtime Database** — FCM token storage, user data, owned units
- **Firebase Cloud Messaging** — iOS push notifications via FCM v1 API
- **Google Cloud Run** — bidirectional sync between Odoo and Firebase
- **Dropbox API** — OAuth2 scoped app for product image folder links
- **SwiftUI/iOS** — mobile client consuming this API

## System Flow

1. Odoo invoice confirmed → server action triggers Google Cloud Run
2. Cloud Run calculates rank from owned weight → writes to Firebase + back to Odoo
3. If rank changed → Cloud Run calls FastAPI `/notify/user/{partner_id}` automatically
4. iOS app login → FCM token registered via `/register-token` → stored in Firebase
5. FastAPI delivers push notification to all user devices via FCM v1 API
6. iOS requests product image → FastAPI calls Dropbox API → returns shared folder URL

## Environment Variables (Railway)

| Variable | Purpose |
|----------|---------|
| `ODOO_URL` | Odoo instance URL |
| `ODOO_DB` | Odoo database name |
| `ODOO_USER` | Odoo admin user |
| `ODOO_PASSWORD` | Odoo admin password |
| `FIREBASE_SERVICE_ACCOUNT` | Base64-encoded Firebase service account JSON |
| `DROPBOX_TOKEN` | Dropbox OAuth2 access token (auto-refreshed) |
| `DROPBOX_REFRESH_TOKEN` | Dropbox OAuth2 refresh token |
| `DROPBOX_APP_KEY` | Dropbox app key |
| `DROPBOX_APP_SECRET` | Dropbox app secret |
| `CACHE_BUST` | Increment to force Railway rebuild |

## Security

- Credentials stored in `.env` — never committed
- Railway environment variables used in production
- Firebase service account authenticated via OAuth2
- Dropbox access token auto-refreshed server-side — never exposed to iOS client
- `.gitignore` configured to exclude all secrets

## Local Setup
```bash
git clone https://github.com/javiergomezgit/myez-odoo-api
cd myez-odoo-api
cp .env.example .env  # add your credentials
pip install -r requirements.txt
uvicorn main:app --reload
```

## Author
Javier Gomez — Senior Software Engineer

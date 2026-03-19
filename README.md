# MyEZ Integration Layer — Odoo + FastAPI + iOS

FastAPI backend serving as the integration layer between Odoo ERP (XML-RPC)
and the MyEZ iOS client. Exposes clean REST endpoints consumed by the mobile
app, with environment-based credential management and cloud deployment via Railway.

## Live API
https://myez-odooapi-production.up.railway.app

## Architecture

graph TD
    subgraph iOS["📱 iOS Client (SwiftUI)"]
        A[DealsView]
        B[Pull to Refresh]
        C[Loading / Error State]
    end

    subgraph Railway["☁️ Railway (PaaS)"]
        D[FastAPI Middleware]
        E[GET /ping]
        F[GET /odoo/ping]
        G[GET /odoo/clients]
        H[GET /odoo/clients/ranking]
    end

    subgraph Odoo["🗄️ Odoo ERP"]
        I[res.partner]
        J[x_studio_rank_weight]
    end

    subgraph Planned["🔜 Planned"]
        L[Firebase Notifications]
    end

    A -->|REST HTTP GET| D
    B --> A
    C --> A
    D -->|XML-RPC| I
    D -->|XML-RPC| J
    H --> J
    G --> I
    D -.->|planned| L

    subgraph Config["🔐 Config"]
        M[.env — credentials]
        N[Railway env vars]
    end

    M --> D
    N --> D

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ping` | Health check — confirms API is live |
| GET | `/odoo/ping` | Odoo auth check — confirms XML-RPC connection |
| GET | `/odoo/clients` | Returns live client list from Odoo |
| GET | `/odoo/clients/ranking` | Returns clients ranked by inflatable weight owned. Null values handled as "No Rank Yet", ranked clients sorted first. |
| POST | `/notify` | Sends Firebase push notification to iOS device via FCM v1 API. Params: `token`, `title`, `body` |
| POST | `/register-token` | Registers a device FCM token for a user in Firebase Realtime Database. Supports multiple devices per user. Params: partner_id, token |
| POST | `/notify/user/{partner_id}` | Sends push notification to all registered devices for an Odoo partner. Params: title, body
| POST | `/odoo/check-rank-changes` | Reads owned weight from Firebase, detects rank tier changes, sends rank-up notifications, and updates rank cache. |

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

## Stack

- **FastAPI** — REST API middleware layer
- **Odoo XML-RPC** — ERP data source (res.partner, account.move)
- **Railway** — PaaS cloud deployment
- **Firebase Realtime Database** — FCM token storage, rank cache, user data
- **Firebase Cloud Messaging** — iOS push notifications via FCM v1 API
- **Google Cloud Run** — Odoo → Firebase bidirectional sync service
- **SwiftUI/iOS** — mobile client consuming this API

## System Flow

1. Odoo invoice confirmed → server action triggers Google Cloud Run
2. Cloud Run calculates rank from owned weight → writes to Firebase + back to Odoo
3. If rank changed → Cloud Run calls FastAPI /notify/user/{partner_id} automatically
4. iOS app login → FCM token registered via /register-token → stored in Firebase
5. FastAPI delivers push notification to all user devices via FCM v1 API

## Security

- Credentials stored in `.env` — never committed
- Railway environment variables used in production
- `.gitignore` configured to exclude all secrets

## Local Setup
```bash
git clone https://github.com/javiergomezgit/myez-odoo-api
cd myez-odoo-api
cp .env.example .env  # add your Odoo credentials
pip install -r requirements.txt
uvicorn main:app --reload
```

## Author
Javier Gomez — Senior Software Engineer

# MyEZ Integration Layer — Odoo + FastAPI + iOS

FastAPI backend serving as the integration layer between Odoo ERP (XML-RPC)
and the MyEZ iOS client. Exposes clean REST endpoints consumed by the mobile
app, with environment-based credential management and cloud deployment via Railway.

## Live API
https://myez-odoo-api-production-87b0.up.railway.app

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

## Stack

- **FastAPI** — REST API middleware layer
- **Odoo XML-RPC** — ERP data source (res.partner, custom rank weight field)
- **Railway** — PaaS cloud deployment
- **SwiftUI/iOS** — mobile client consuming this API
- **Firebase** — push notifications (planned)

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

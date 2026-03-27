from fastapi import FastAPI
from dotenv import load_dotenv
from google.oauth2 import service_account
import google.auth.transport.requests
import xmlrpc.client
import urllib.request
import urllib.error
import base64
import json
import os

load_dotenv()

app = FastAPI()

# ================================================================
# CONFIGURATION
# Environment variables — set in .env locally, Railway in production
# ================================================================

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")
FIREBASE_DB_URL = "https://myezfirebase.firebaseio.com"

# Rank tier thresholds in lbs — used for gamification logic
RANK_TIERS = [
    (2500, "Minimumweight"),
    (5000, "Flyweight"),
    (7500, "Bantamweight"),
    (10000, "Featherweight"),
    (12500, "Lightweight"),
    (15000, "Welterweight"),
    (17500, "Middleweight"),
    (20000, "Cruiserweight"),
    (float("inf"), "Heavyweight"),
]


# ================================================================
# HELPERS
# Shared utility functions used across multiple endpoints
# ================================================================

def get_db_token():
    """Returns OAuth token scoped for Firebase Realtime Database access."""
    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if key_json:
        key_dict = json.loads(base64.b64decode(key_json).decode("utf-8"))
        credentials = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/firebase.database",
                    "https://www.googleapis.com/auth/userinfo.email"]
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            "security/firebase-service-account.json",
            scopes=["https://www.googleapis.com/auth/firebase.database",
                    "https://www.googleapis.com/auth/userinfo.email"]
        )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def get_access_token():
    """Returns a short-lived OAuth2 access token for authenticating FCM API requests."""
    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if key_json:
        key_dict = json.loads(base64.b64decode(key_json).decode("utf-8"))
        credentials = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            "security/firebase-service-account.json",
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def get_rank(weight: int) -> str:
    """Returns the rank tier name based on total owned weight in lbs."""
    for threshold, rank in RANK_TIERS:
        if weight < threshold:
            return rank
    return "Heavyweight"


def odoo_authenticate():
    """Authenticates with Odoo via XML-RPC and returns (uid, models proxy)."""
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


# ================================================================
# HEALTH CHECK
# Used to verify API and Odoo connectivity
# ================================================================

@app.get("/ping")
def ping():
    """Health check — confirms the API is live."""
    return {"status": "ok"}


@app.get("/odoo/ping")
def odoo_ping():
    """Odoo auth check — confirms XML-RPC connection to Odoo is working."""
    uid, _ = odoo_authenticate()
    return {"odoo_uid": uid}


# ================================================================
# CLIENTS
# Endpoints for customer data from Odoo and Firebase
# ================================================================

@app.get("/odoo/clients")
def get_clients():
    """Returns a list of active customers from Odoo with name, email, and phone."""
    uid, models = odoo_authenticate()
    clients = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'res.partner', 'search_read',
        [[['customer_rank', '>', 0]]],
        {'fields': ['name', 'email', 'phone'], 'limit': 5}
    )
    return {"clients": clients}


@app.get("/odoo/clients/ranking")
def get_client_ranking():
    """Returns clients ranked by inflatable weight owned. Null ranks handled as 'No Rank Yet', ranked clients sorted first."""
    uid, models = odoo_authenticate()
    clients = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'res.partner', 'search_read',
        [[['customer_rank', '>', 0]]],
        {'fields': ['name', 'x_studio_rank_weight'], 'limit': 30}
    )
    result = [
        {
            "id": c["id"],
            "name": c["name"],
            "rank_weight": c["x_studio_rank_weight"] if c["x_studio_rank_weight"] not in [False, None, ""] else "No Rank Yet"
        }
        for c in clients
    ]
    return {"clients": result}


@app.get("/clients/owned-units/{partner_id}")
def get_owned_units(partner_id: int):
    """Returns owned inflatable units, total weight, and rank tier for a specific customer from Firebase."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/users/{partner_id}.json?auth={db_token}"

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except:
        return {"success": False, "error": "Failed to fetch user data"}

    if not data:
        return {"success": False, "error": "User not found"}

    return {
        "success": True,
        "partner_id": partner_id,
        "owned_weight": data.get("owned_weight", 0),
        "rank": data.get("typeuser", "minimumweight"),
        "units": data.get("units", {})
    }


# ================================================================
# PRODUCTS
# Endpoints for product catalog from Odoo shop
# Endpoints for png links of the products from Dropbox
# Future: add /products/categories, /products/search, /products/featured
# ================================================================

@app.get("/products")
def get_products():
    """Returns published products from Odoo shop with name, price, category, and image URL."""
    uid, models = odoo_authenticate()
    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'product.template', 'search_read',
        [[['is_published', '=', True], ['sale_ok', '=', True]]],
        {'fields': ['name', 'list_price', 'description_sale', 'categ_id', 'image_1920'], 'limit': 50}
    )
    result = []
    for p in products:
        result.append({
            "id": p["id"],
            "name": p["name"],
            "price": p["list_price"],
            "description": p["description_sale"] or "",
            "category": p["categ_id"][1] if p["categ_id"] else "Uncategorized",
            "image_url": f"{ODOO_URL}/web/image/product.template/{p['id']}/image_1920"
        })
    return {"products": result}


@app.get("/products/{product_id}")
def get_product(product_id: int):
    """Returns full details for a single product by ID."""
    uid, models = odoo_authenticate()
    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'product.template', 'search_read',
        [[['id', '=', product_id]]],
        {'fields': ['name', 'list_price', 'description_sale', 'categ_id', 'image_1920']}
    )
    if not products:
        return {"success": False, "error": "Product not found"}
    p = products[0]
    return {
        "success": True,
        "id": p["id"],
        "name": p["name"],
        "price": p["list_price"],
        "description": p["description_sale"] or "",
        "category": p["categ_id"][1] if p["categ_id"] else "Uncategorized",
        "image_url": f"{ODOO_URL}/web/image/product.template/{p['id']}/image_1920"
    }


@app.get("/products/image/{sku}")
def get_product_image(sku: str):
    token = os.getenv("DROPBOX_TOKEN")
    if not token:
        return {"error": "Dropbox token not configured"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    folder_path = f"/EZ Inflatables Dropbox/Javier Gomez/MainImages (1)/{sku}/{sku}-PNG"

    # Try to create a shared link
    link_resp = requests.post(
        "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
        headers=headers,
        json={"path": folder_path}
    )

    # If link already exists, fetch it instead
    if link_resp.status_code == 409:
        existing_resp = requests.post(
            "https://api.dropboxapi.com/2/sharing/list_shared_links",
            headers=headers,
            json={"path": folder_path, "direct_only": True}
        )
        links = existing_resp.json().get("links", [])
        if links:
            return {"url": links[0]["url"], "sku": sku}
        return {"error": "Could not retrieve shared link", "sku": sku}

    if link_resp.status_code != 200:
        return {"error": "Folder not found", "sku": sku}

    return {"url": link_resp.json().get("url"), "sku": sku}


# ================================================================
# NOTIFICATIONS
# FCM push notification endpoints — token registration and delivery
# Future: add /notify/broadcast (all users), /notify/rank/{rank_tier}
# ================================================================

@app.post("/register-token")
def register_token(partner_id: int, token: str):
    """Registers a device FCM token under users/{partner_id}/fcmTokens in Firebase. Supports multiple devices per user."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/users/{partner_id}/fcmTokens.json?auth={db_token}"

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            tokens = data if isinstance(data, list) else []
    except:
        tokens = []

    if token not in tokens:
        tokens.append(token)

    payload = json.dumps(tokens).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as response:
        response.read()

    return {"success": True, "partner_id": partner_id, "devices": len(tokens)}


@app.post("/notify")
def send_notification(token: str, title: str, body: str):
    """Sends a push notification to a specific device using its FCM token."""
    try:
        access_token = get_access_token()
        project_id = "myezfirebase"
        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        payload = json.dumps({
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "apns": {"headers": {"apns-environment": "development"}}
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            return {"success": True, "message_id": result.get("name")}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": e.read().decode()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/notify/user/{partner_id}")
def notify_user(partner_id: int, title: str, body: str):
    """Sends a push notification to all registered devices for a given Odoo partner ID."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/users/{partner_id}/fcmTokens.json?auth={db_token}"

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            tokens = data if isinstance(data, list) else []
    except:
        return {"success": False, "error": "Failed to fetch tokens"}

    if not tokens:
        return {"success": False, "error": "No devices registered for this user"}

    access_token = get_access_token()
    project_id = "myezfirebase"
    fcm_url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    results = []

    for token in tokens:
        try:
            payload = json.dumps({
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                    "apns": {"headers": {"apns-environment": "development"}}
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                fcm_url, data=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req) as response:
                results.append({"token": token[:20], "success": True})
        except urllib.error.HTTPError as e:
            results.append({"token": token[:20], "success": False, "error": e.read().decode()})

    return {"success": True, "results": results}


# ================================================================
# GAMIFICATION — RANK CHANGES
# Manual bulk rank check — useful for backfill or admin triggers
# Automatic rank change detection is handled by Google Cloud Run
# ================================================================

@app.post("/odoo/check-rank-changes")
def check_rank_changes():
    """Manual bulk check — reads owned_weight from Firebase, detects rank tier changes, sends push notifications."""
    db_token = get_db_token()

    # Fetch all users from Firebase
    users_url = f"{FIREBASE_DB_URL}/users.json?auth={db_token}"
    req = urllib.request.Request(users_url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            users = json.loads(response.read().decode()) or {}
    except:
        return {"success": False, "error": "Failed to fetch users from Firebase"}

    # Fetch rank cache
    ranks_url = f"{FIREBASE_DB_URL}/rank_cache.json?auth={db_token}"
    req = urllib.request.Request(ranks_url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            rank_cache = json.loads(response.read().decode()) or {}
    except:
        rank_cache = {}

    notifications_sent = []
    updated_cache = dict(rank_cache)

    for partner_id, user_data in users.items():
        if not isinstance(user_data, dict):
            continue

        name = user_data.get("name", "Customer")
        weight = user_data.get("owned_weight", 0)

        try:
            weight = int(float(str(weight))) if weight not in [False, None, ""] else 0
        except (ValueError, TypeError):
            weight = 0

        current_rank = get_rank(weight)
        previous_rank = rank_cache.get(str(partner_id))

        if previous_rank and previous_rank != current_rank:
            tokens = user_data.get("fcmTokens", [])
            if not isinstance(tokens, list):
                tokens = []

            if tokens:
                access_token = get_access_token()
                fcm_url = f"https://fcm.googleapis.com/v1/projects/myezfirebase/messages:send"
                for token in tokens:
                    try:
                        payload = json.dumps({
                            "message": {
                                "token": token,
                                "notification": {
                                    "title": "🏆 Rank Up!",
                                    "body": f"Congratulations {name}! You reached {current_rank}!"
                                },
                                "apns": {"headers": {"apns-environment": "development"}}
                            }
                        }).encode("utf-8")
                        req = urllib.request.Request(
                            fcm_url, data=payload,
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Content-Type": "application/json"
                            },
                            method="POST"
                        )
                        with urllib.request.urlopen(req) as response:
                            pass
                    except urllib.error.HTTPError:
                        pass

                notifications_sent.append({
                    "partner_id": partner_id,
                    "name": name,
                    "previous_rank": previous_rank,
                    "current_rank": current_rank
                })

        updated_cache[str(partner_id)] = current_rank

    # Save updated rank cache
    payload = json.dumps(updated_cache).encode("utf-8")
    req = urllib.request.Request(ranks_url, data=payload, method="PUT")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as response:
        response.read()

    return {
        "success": True,
        "checked": len(users),
        "notifications_sent": len(notifications_sent),
        "changes": notifications_sent
    }


# ================================================================
# FUTURE — AUTH
# Add login/signup endpoints here to replace direct Odoo XML-RPC from iOS
# POST /auth/login   — email + password → returns user profile + session
# POST /auth/signup  — name + email + password → creates Odoo user
# ================================================================


# ================================================================
# FUTURE — ORDERS
# Add order history endpoints here
# GET /orders/{partner_id}         — returns order history from Odoo
# GET /orders/{partner_id}/{order_id} — returns single order detail
# ================================================================


# ================================================================
# FUTURE — CART / CHECKOUT
# Add cart and checkout endpoints here if moving away from WebView
# POST /cart/add     — add product to cart
# POST /cart/remove  — remove product from cart
# POST /checkout     — submit order to Odoo
# ================================================================

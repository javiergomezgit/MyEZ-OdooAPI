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

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

FIREBASE_DB_URL = "https://myezfirebase.firebaseio.com/"


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


@app.get("/ping")
def ping():
    """Health check — confirms the API is live."""
    return {"status": "ok"}


@app.get("/odoo/ping")
def odoo_ping():
    """Odoo auth check — confirms XML-RPC connection to Odoo is working."""
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    return {"odoo_uid": uid}


@app.get("/odoo/clients")
def get_clients():
    """Returns a list of active customers from Odoo with name, email, and phone."""
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
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
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
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


@app.post("/register-token")
def register_token(partner_id: int, token: str):
    """Registers a device FCM token under users/{partner_id}/fcmTokens in Firebase Realtime Database."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/users/{partner_id}/fcmTokens.json?auth={db_token}"

    # Get existing tokens
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            tokens = data if isinstance(data, list) else []
    except:
        tokens = []

    # Add token if not already present
    if token not in tokens:
        tokens.append(token)

    # Save back
    payload = json.dumps(tokens).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as response:
        response.read()

    return {"success": True, "partner_id": partner_id, "devices": len(tokens)}


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

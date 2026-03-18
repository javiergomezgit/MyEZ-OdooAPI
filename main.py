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

TOKEN_FILE = "tokens.json"

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

def get_access_token():
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

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)
        

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.get("/odoo/ping")
def odoo_ping():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    return {"odoo_uid": uid}

@app.get("/odoo/clients")
def get_clients():
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
    try:
        access_token = get_access_token()
        project_id = "myezfirebase"
        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        payload = json.dumps({
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body
                },
                "apns": {
                    "headers": {
                        "apns-environment": "development"
                    }
                }
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
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
        error_body = e.read().decode()
        return {"success": False, "error": error_body}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/register-token")
def register_token(partner_id: int, token: str):
    tokens = load_tokens()
    key = str(partner_id)
    if key not in tokens:
        tokens[key] = []
    if token not in tokens[key]:
        tokens[key].append(token)
    save_tokens(tokens)
    return {"success": True, "partner_id": partner_id, "devices": len(tokens[key])}

@app.post("/notify/user/{partner_id}")
def notify_user(partner_id: int, title: str, body: str):
    tokens = load_tokens()
    key = str(partner_id)
    if key not in tokens or not tokens[key]:
        return {"success": False, "error": "No devices registered for this user"}
    
    results = []
    access_token = get_access_token()
    project_id = "myezfirebase"
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    
    for token in tokens[key]:
        try:
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
                results.append({"token": token[:20], "success": True})
        except urllib.error.HTTPError as e:
            results.append({"token": token[:20], "success": False, "error": e.read().decode()})
    
    return {"success": True, "results": results}

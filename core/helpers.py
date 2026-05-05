import base64
import hashlib
import hmac
import json
import os
import secrets
import string
import urllib.request
import xmlrpc.client

import google.auth.transport.requests
import requests
from google.oauth2 import service_account

from core.config import (
    FIREBASE_DB_URL,
    ODOO_DB,
    ODOO_PASSWORD,
    ODOO_URL,
    ODOO_USER,
    RANK_TIERS,
    SHOPIFY_WEBHOOK_SECRET,
)


# ----------------------------------------------------------------
# ODOO
# ----------------------------------------------------------------

def odoo_authenticate():
    """Authenticates with Odoo via XML-RPC and returns (uid, models proxy)."""
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


# ----------------------------------------------------------------
# FIREBASE
# ----------------------------------------------------------------

def get_db_token():
    """Returns OAuth token scoped for Firebase Realtime Database access."""
    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if key_json:
        key_dict = json.loads(base64.b64decode(key_json).decode("utf-8"))
        credentials = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=[
                "https://www.googleapis.com/auth/firebase.database",
                "https://www.googleapis.com/auth/userinfo.email",
            ],
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            "security/firebase-service-account.json",
            scopes=[
                "https://www.googleapis.com/auth/firebase.database",
                "https://www.googleapis.com/auth/userinfo.email",
            ],
        )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def firebase_write(path: str, data: dict):
    """Writes data to Firebase Realtime Database at the given path."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/{path}.json?auth={db_token}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())


def firebase_read(path: str):
    """Reads data from Firebase Realtime Database at the given path."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/{path}.json?auth={db_token}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())


# ----------------------------------------------------------------
# FCM
# ----------------------------------------------------------------

def get_access_token():
    """Returns a short-lived OAuth2 access token for FCM API requests."""
    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if key_json:
        key_dict = json.loads(base64.b64decode(key_json).decode("utf-8"))
        credentials = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            "security/firebase-service-account.json",
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def send_fcm(token: str, title: str, body: str) -> dict:
    """Sends a single FCM push notification to a device token."""
    import urllib.error

    access_token = get_access_token()
    project_id = "myezfirebase"
    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    payload = json.dumps({
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "apns": {"headers": {"apns-environment": "development"}},
        }
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            return {"success": True, "message_id": result.get("name")}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": e.read().decode()}


# ----------------------------------------------------------------
# DROPBOX
# ----------------------------------------------------------------

def get_dropbox_token() -> str:
    """Returns a valid Dropbox access token, refreshing if expired."""
    token = os.getenv("DROPBOX_TOKEN")
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")
    app_key = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")

    test = requests.post(
        "https://api.dropboxapi.com/2/users/get_current_account",
        headers={"Authorization": f"Bearer {token}"},
    )
    if test.status_code == 200:
        return token

    resp = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        auth=(app_key, app_secret),
        data={"refresh_token": refresh_token, "grant_type": "refresh_token"},
    )
    return resp.json().get("access_token")


# ----------------------------------------------------------------
# GAMIFICATION
# ----------------------------------------------------------------

def get_rank(weight: int) -> str:
    """Returns the rank tier name based on total owned weight in lbs."""
    for threshold, rank in RANK_TIERS:
        if weight < threshold:
            return rank
    return "Heavyweight"


# ----------------------------------------------------------------
# SHOPIFY
# ----------------------------------------------------------------

def generate_temp_password(length: int = 10) -> str:
    """Generates a random temporary password with letters, digits, and symbols."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def verify_shopify_webhook(body: bytes, hmac_header: str) -> bool:
    """Verifies Shopify webhook signature using HMAC-SHA256."""
    secret = SHOPIFY_WEBHOOK_SECRET or ""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(computed, hmac_header)

import json
import urllib.error
import urllib.request

from fastapi import APIRouter

from core.config import FIREBASE_DB_URL
from core.helpers import firebase_read, get_db_token, send_fcm

router = APIRouter(prefix="/notify", tags=["Notifications"])


@router.post("/register-token")
def register_token(partner_id: int, token: str):
    """Registers a device FCM token under users/{partner_id}/fcmTokens in Firebase."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/users/{partner_id}/fcmTokens.json?auth={db_token}"

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            tokens = data if isinstance(data, list) else []
    except Exception:
        tokens = []

    if token not in tokens:
        tokens.append(token)

    payload = json.dumps(tokens).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as response:
        response.read()

    return {"success": True, "partner_id": partner_id, "devices": len(tokens)}


@router.post("")
def send_notification(token: str, title: str, body: str):
    """Sends a push notification to a specific device using its FCM token."""
    return send_fcm(token, title, body)


@router.post("/user/{partner_id}")
def notify_user(partner_id: int, title: str, body: str):
    """Sends a push notification to all registered devices for a given Odoo partner ID."""
    db_token = get_db_token()
    url = f"{FIREBASE_DB_URL}/users/{partner_id}/fcmTokens.json?auth={db_token}"

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            tokens = data if isinstance(data, list) else []
    except Exception:
        return {"success": False, "error": "Failed to fetch tokens"}

    if not tokens:
        return {"success": False, "error": "No devices registered for this user"}

    results = [send_fcm(token, title, body) for token in tokens]
    return {"success": True, "results": results}

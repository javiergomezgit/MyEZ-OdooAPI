import json
import urllib.request

from fastapi import APIRouter

from core.config import FIREBASE_DB_URL
from core.helpers import get_db_token, get_rank, send_fcm

router = APIRouter(prefix="/gamification", tags=["Gamification"])


@router.post("/check-rank-changes")
def check_rank_changes():
    """Manual bulk check — reads owned_weight from Firebase, detects rank tier changes, sends push notifications."""
    db_token = get_db_token()

    # Fetch all users
    users_url = f"{FIREBASE_DB_URL}/users.json?auth={db_token}"
    req = urllib.request.Request(users_url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            users = json.loads(response.read().decode()) or {}
    except Exception:
        return {"success": False, "error": "Failed to fetch users from Firebase"}

    # Fetch rank cache
    ranks_url = f"{FIREBASE_DB_URL}/rank_cache.json?auth={db_token}"
    req = urllib.request.Request(ranks_url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            rank_cache = json.loads(response.read().decode()) or {}
    except Exception:
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

            for token in tokens:
                send_fcm(
                    token,
                    title="🏆 Rank Up!",
                    body=f"Congratulations {name}! You reached {current_rank}!",
                )

            notifications_sent.append({
                "partner_id": partner_id,
                "name": name,
                "previous_rank": previous_rank,
                "current_rank": current_rank,
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
        "changes": notifications_sent,
    }

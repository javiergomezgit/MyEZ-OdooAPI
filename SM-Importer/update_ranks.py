"""
Update Ranks Script — Phase 1
==============================
Reads all users from Firebase Realtime Database and:
1. Calculates correct rank tier based on owned_weight
2. Updates typeuser if rank changed
3. Adds rank_update/{timestamp}: rank_name entry (history preserved)
4. Sends FCM push notification to all registered devices on rank-up

Rank Tiers (cumulative owned weight in lbs):
  0    - 999   → minimumweight
  1000 - 1999  → flyweight
  2000 - 3999  → bantamweight
  4000 - 5999  → featherweight
  6000 - 8999  → lightweight
  9000 - 12999 → middleweight
  13000+       → heavyweight

Usage:
    python3 update_ranks.py

Requirements:
    pip install firebase-admin python-dotenv google-auth --break-system-packages
"""

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

import firebase_admin
from firebase_admin import credentials, db


# ----------------------------------------------------------------
# FIREBASE SETUP
# ----------------------------------------------------------------

def init_firebase():
    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if key_json:
        key_dict = json.loads(base64.b64decode(key_json).decode("utf-8"))
        cred = credentials.Certificate(key_dict)
    else:
        cred = credentials.Certificate("security/firebase-service-account.json")

    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://myezfirebase.firebaseio.com"
    })
    print("✅ Firebase initialized\n")


# ----------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------

RANK_TIERS = [
    (1000,  "minimumweight"),
    (2000,  "flyweight"),
    (4000,  "bantamweight"),
    (6000,  "featherweight"),
    (9000,  "lightweight"),
    (13000, "middleweight"),
    (float("inf"), "heavyweight"),
]

FCM_PROJECT_ID = "myezfirebase"


# ----------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------

def get_rank(weight):
    """Return rank tier name based on cumulative owned weight."""
    for threshold, rank in RANK_TIERS:
        if weight < threshold:
            return rank
    return "heavyweight"


def get_access_token():
    """Get OAuth2 access token for FCM API."""
    import google.auth.transport.requests
    from google.oauth2 import service_account

    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if key_json:
        key_dict = json.loads(base64.b64decode(key_json).decode("utf-8"))
        cred = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    else:
        cred = service_account.Credentials.from_service_account_file(
            "security/firebase-service-account.json",
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    request = google.auth.transport.requests.Request()
    cred.refresh(request)
    return cred.token


def send_rank_notifications(uid, name, new_rank, fcm_tokens):
    """Send FCM push to all registered devices for a user."""
    if not fcm_tokens or not isinstance(fcm_tokens, dict):
        print(f"  → No FCM tokens registered — skipping notification")
        return

    try:
        access_token = get_access_token()
        url = f"https://fcm.googleapis.com/v1/projects/{FCM_PROJECT_ID}/messages:send"
        sent = 0
        failed = 0

        for device_key, token in fcm_tokens.items():
            if not token:
                continue
            payload = json.dumps({
                "message": {
                    "token": token,
                    "notification": {
                        "title": "🏆 Rank Up!",
                        "body": f"Congratulations {name}! You reached {new_rank.capitalize()}!"
                    },
                    "apns": {"headers": {"apns-environment": "production"}}
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                url, data=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req) as response:
                    sent += 1
                    print(f"  → FCM sent to device {device_key[:8]}... ✅")
            except urllib.error.HTTPError as e:
                failed += 1
                print(f"  → FCM failed for device {device_key[:8]}...: {e.read().decode()}")

        print(f"  → Notifications: {sent} sent, {failed} failed")

    except Exception as e:
        print(f"  ⚠ FCM error: {e}")


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------

def run_update_ranks():
    print("📊 Reading all users from Firebase...\n")

    ref = db.reference("users")
    all_users = ref.get()

    if not all_users:
        print("❌ No users found in Firebase.")
        return

    updated   = []
    unchanged = []
    errors    = []

    now = int(datetime.now(timezone.utc).timestamp())

    for uid, profile in all_users.items():
        if not isinstance(profile, dict):
            continue

        email        = profile.get("email", "")
        name         = profile.get("name", "Customer")
        owned_weight = int(profile.get("owned_weight", 0))
        current_rank = profile.get("typeuser", "minimumweight")
        correct_rank = get_rank(owned_weight)
        fcm_tokens   = profile.get("fcmTokens", {})

        print(f"[{email}] weight={owned_weight} | current={current_rank} | correct={correct_rank}")

        if current_rank == correct_rank:
            print(f"  → No change")
            unchanged.append({"uid": uid, "email": email, "rank": current_rank})
            continue

        # Rank changed — update typeuser, add history entry, send FCM
        try:
            user_ref = db.reference(f"users/{uid}")
            user_ref.update({
                "typeuser": correct_rank,
                f"rank_update/{now}": correct_rank,
            })
            print(f"  → 🏆 Rank updated: {current_rank} → {correct_rank}")
            print(f"  → rank_update/{now} = {correct_rank}")

            # Send push notification
            send_rank_notifications(uid, name, correct_rank, fcm_tokens)

            updated.append({
                "uid": uid,
                "email": email,
                "previous_rank": current_rank,
                "new_rank": correct_rank,
                "weight": owned_weight,
            })

        except Exception as e:
            print(f"  ❌ Error updating {email}: {e}")
            errors.append({"uid": uid, "email": email, "error": str(e)})

    # ----------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print("RANK UPDATE SUMMARY")
    print(f"{'=' * 50}")
    print(f"🏆 Rank updated:  {len(updated)}")
    print(f"✅ No change:     {len(unchanged)}")
    print(f"❌ Errors:        {len(errors)}")

    if updated:
        print("\nRank Changes:")
        for u in updated:
            print(f"  {u['email']} | {u['weight']} lbs | {u['previous_rank']} → {u['new_rank']}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e['email']} → {e['error']}")


# ----------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------

if __name__ == "__main__":
    init_firebase()
    run_update_ranks()

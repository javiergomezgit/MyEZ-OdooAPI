"""
Update Leaderboard Script — Phase 1
=====================================
Reads all users and their transactions from Firebase and:
1. Groups transactions by month (from createdOn timestamp)
2. Calculates score per user per month:
   - type_score "weight": int(weight * 0.25)
   - type_score "money": int(total * 0.50)
3. Writes to leaderboards/{month}/{uid}/
   - score: int
   - display: company name if exists, else zip code
4. Single leaderboard per month — no tier separation
5. Recalculates from scratch every run — always produces correct result

Run order:
  1. sm_customers.py
  2. sm_purchases.py
  3. update_ranks.py
  4. update_leaderboard.py (this file)

Usage:
    python3 update_leaderboard.py

Requirements:
    pip install firebase-admin python-dotenv --break-system-packages
"""

import base64
import json
import os
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
# HELPERS
# ----------------------------------------------------------------

def timestamp_to_month(ts):
    """Convert Unix timestamp to '2026-06' format."""
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m")


def get_display(profile):
    """Return company name if exists, else zip code only."""
    company = (profile.get("company_name") or "").strip()
    if company:
        return company
    return (profile.get("zipCode") or "").strip()


def calculate_score(transaction):
    """
    Calculate score for a single transaction.
    - type_score "weight": int(weight * 0.25)
    - type_score "money": int(total * 0.50)
    """
    weight     = int(transaction.get("weight", 0))
    total      = int(transaction.get("total", 0))
    type_score = transaction.get("type_score", "money")

    if type_score == "weight":
        return int(weight * 0.25)
    return int(total * 0.50)


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------

def run_update_leaderboard():
    print("📊 Reading all users from Firebase...\n")

    ref = db.reference("users")
    all_users = ref.get()

    if not all_users:
        print("❌ No users found in Firebase.")
        return

    # leaderboard_data[month][uid] = {score, display}
    leaderboard_data = {}

    processed_users = 0
    skipped_users   = 0

    for uid, profile in all_users.items():
        if not isinstance(profile, dict):
            continue

        email        = profile.get("email", "")
        display      = get_display(profile)
        transactions = profile.get("transactions", {})

        if not transactions or not isinstance(transactions, dict):
            print(f"  ⚠ {email} — no transactions, skipping")
            skipped_users += 1
            continue

        print(f"[{email}] transactions={len(transactions)}")

        # Accumulate score per month
        monthly_scores = {}  # month -> score

        for txn_id, txn in transactions.items():
            if not isinstance(txn, dict):
                continue

            created_on = txn.get("createdOn", 0)
            month      = timestamp_to_month(created_on)
            score      = calculate_score(txn)

            if month not in monthly_scores:
                monthly_scores[month] = 0
            monthly_scores[month] += score

            print(f"  → txn={txn_id} | month={month} | score={score}")

        # Add to leaderboard structure
        for month, score in monthly_scores.items():
            if month not in leaderboard_data:
                leaderboard_data[month] = {}

            leaderboard_data[month][uid] = {
                "score": score,
                "display": display,
            }

        processed_users += 1

    # ----------------------------------------------------------------
    # WRITE TO FIREBASE
    # ----------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print("WRITING LEADERBOARD TO FIREBASE")
    print(f"{'=' * 50}\n")

    written = 0
    errors  = []

    for month, users in leaderboard_data.items():
        try:
            ref = db.reference(f"leaderboards/{month}")
            ref.set(users)
            print(f"✅ leaderboards/{month} — {len(users)} users")
            written += 1
        except Exception as e:
            print(f"❌ Error writing leaderboards/{month}: {e}")
            errors.append({"month": month, "error": str(e)})

    # ----------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print("LEADERBOARD UPDATE SUMMARY")
    print(f"{'=' * 50}")
    print(f"👤 Users processed:   {processed_users}")
    print(f"⏭  Users skipped:     {skipped_users}")
    print(f"✅ Months written:    {written}")
    print(f"❌ Errors:            {len(errors)}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e['month']} → {e['error']}")


# ----------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------

if __name__ == "__main__":
    init_firebase()
    run_update_leaderboard()

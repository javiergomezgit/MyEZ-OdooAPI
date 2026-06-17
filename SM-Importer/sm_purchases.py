"""
Sales Master Purchases Import Script — Phase 1
===============================================
Reads an ordered items CSV from Sales Master and:
1. Matches customer by email to Firebase Auth
2. Skips if transaction_id already exists in Firebase
3. Red flags weight == 0 and total > 1000 (data entry error)
4. Writes raw transaction to users/{uid}/transactions/{transaction_id}/
5. Updates users/{uid}/units/{SKU}: qty (weight >= 54 only)
6. Updates users/{uid}/owned_weight (weight >= 54 only)
7. Calculates and stores score per transaction:
   - weight >= 54 (inflatable): int(weight * 0.25)
   - weight < 54 (accessory/money): int(total * 0.50)

Does NOT update: typeuser, leaderboard, FCM — handled by update_ranks.py

Usage:
    python3 sm_purchases.py --csv path/to/ordered_items.csv

Requirements:
    pip install firebase-admin python-dotenv --break-system-packages
"""

import argparse
import base64
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

import firebase_admin
from firebase_admin import auth, credentials, db


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
# WEIGHT THRESHOLD
# ----------------------------------------------------------------
INFLATABLE_WEIGHT_THRESHOLD = 54  # lbs — items at or above this are inflatables


# ----------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------

def clean_total(total_str):
    if not total_str:
        return 0
    cleaned = re.sub(r"[^\d.]", "", total_str.strip())
    try:
        return int(float(cleaned))
    except Exception:
        return 0


def clean_weight(weight_str):
    if not weight_str or weight_str.strip() == "":
        return 0
    try:
        return float(weight_str.strip())
    except Exception:
        return 0


def clean_email(email_str):
    if not email_str:
        return ""
    return email_str.strip().lower().split(",")[0].strip()


def parse_date_to_unix(date_str):
    if not date_str:
        return int(datetime.now(timezone.utc).timestamp())
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return int(datetime.now(timezone.utc).timestamp())


def is_inflatable(weight):
    """Returns True if weight qualifies as an inflatable."""
    return weight >= INFLATABLE_WEIGHT_THRESHOLD


def get_uid_by_email(email):
    try:
        user = auth.get_user_by_email(email)
        return user.uid
    except auth.UserNotFoundError:
        return None
    except Exception as e:
        print(f"  ⚠ Auth lookup error: {e}")
        return None


def get_user_profile(uid):
    try:
        ref = db.reference(f"users/{uid}")
        return ref.get()
    except Exception as e:
        print(f"  ⚠ DB read error: {e}")
        return None


def transaction_exists(uid, transaction_id):
    try:
        ref = db.reference(f"users/{uid}/transactions/{transaction_id}")
        return ref.get() is not None
    except Exception:
        return False


def calculate_score(weight, total):
    """
    Calculate score for a single transaction.
    - weight >= 54 (inflatable): int(weight * 0.25)
    - weight < 54 (accessory/money): int(total * 0.50)
    """
    if is_inflatable(weight):
        return int(weight * 0.25)
    else:
        return int(total * 0.50)


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------

def run_purchases(csv_path):
    print(f"📂 Reading: {csv_path}\n")

    user_updates = {}
    skipped = []
    red_flags = []
    processed_rows = 0
    errors = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, start=1):
            transaction_id = (row.get("transaction_id") or "").strip()
            sku            = (row.get("SKU") or "").strip()
            if sku.upper().endswith("-TX"):
                sku = sku[:-3]
            sold_str   = (row.get("Sold") or "").strip()
            total      = clean_total(row.get("Total") or "")
            weight     = clean_weight(row.get("Weight") or "")
            email      = clean_email(row.get("Email") or "")
            created_on = (row.get("Created On") or "").strip()

            print(f"[{i}] txn={transaction_id} | SKU={sku} | weight={weight} | total={total} | {email}")

            # Skip no email
            if not email:
                print(f"  ⚠ No email — skipping")
                skipped.append({"row": i, "txn": transaction_id, "reason": "no email"})
                continue

            # Skip no SKU
            if not sku:
                print(f"  ⚠ No SKU — skipping")
                skipped.append({"row": i, "txn": transaction_id, "email": email, "reason": "no SKU"})
                continue

            # Skip no transaction_id
            if not transaction_id:
                print(f"  ⚠ No transaction_id — skipping")
                skipped.append({"row": i, "txn": transaction_id, "email": email, "reason": "no transaction_id"})
                continue

            # Red flag: weight == 0 and total > 1000
            if weight == 0 and total > 1000:
                print(f"  🚩 RED FLAG: weight=0 but total=${total} > 1000 — data entry error, skipping")
                red_flags.append({"row": i, "txn": transaction_id, "sku": sku, "email": email, "total": total})
                continue

            # Parse sold quantity
            try:
                sold = int(sold_str)
            except Exception:
                sold = 1

            # Look up Firebase UID
            uid = get_uid_by_email(email)
            if not uid:
                print(f"  ⚠ User not found in Firebase Auth — skipping")
                skipped.append({"row": i, "txn": transaction_id, "sku": sku, "email": email, "reason": "user not in Firebase"})
                continue

            # Check if transaction already processed
            if transaction_exists(uid, transaction_id):
                print(f"  → Transaction {transaction_id} already recorded — skipping")
                skipped.append({"row": i, "txn": transaction_id, "sku": sku, "email": email, "reason": f"transaction {transaction_id} already exists"})
                continue

            # Calculate score and weight
            score      = calculate_score(weight, total)
            weight_add = int(weight * sold) if is_inflatable(weight) else 0
            type_score = "weight" if is_inflatable(weight) else "money"

            # Initialize user accumulator
            if uid not in user_updates:
                user_updates[uid] = {
                    "email": email,
                    "skus_with_weight": {},
                    "weight_add": 0,
                    "transactions": {},
                }

            # Accumulate SKU qty (inflatables only)
            if is_inflatable(weight):
                if sku in user_updates[uid]["skus_with_weight"]:
                    user_updates[uid]["skus_with_weight"][sku] += sold
                else:
                    user_updates[uid]["skus_with_weight"][sku] = sold

            # Accumulate weight
            user_updates[uid]["weight_add"] += weight_add

            # Store transaction record
            user_updates[uid]["transactions"][transaction_id] = {
                "sku": sku,
                "qty": sold,
                "weight": int(weight),
                "total": total,
                "score": score,
                "type_score": type_score,
                "createdOn": parse_date_to_unix(created_on),
            }

            print(f"  → Queued: weight_add={weight_add}, score={score}, type={type_score}")
            processed_rows += 1

    # ----------------------------------------------------------------
    # APPLY UPDATES TO FIREBASE
    # ----------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print("APPLYING FIREBASE UPDATES")
    print(f"{'=' * 50}\n")

    updated = []

    for uid, updates in user_updates.items():
        email = updates["email"]
        print(f"Updating: {email} (uid={uid})")

        profile = get_user_profile(uid)
        if not profile:
            print(f"  ❌ Could not read Firebase profile — skipping")
            errors.append({"uid": uid, "email": email, "error": "profile not found"})
            continue

        current_weight = int(profile.get("owned_weight", 0))
        new_weight = current_weight + updates["weight_add"]

        # Build units update
        current_units = profile.get("units", {})
        if not isinstance(current_units, dict):
            current_units = {}
        if "PLACEHOLDER" in current_units:
            del current_units["PLACEHOLDER"]

        if updates["weight_add"] > 0:
            for sku, qty in updates["skus_with_weight"].items():
                if sku in current_units and isinstance(current_units[sku], int):
                    current_units[sku] = current_units[sku] + qty
                else:
                    current_units[sku] = qty

        try:
            ref = db.reference(f"users/{uid}")
            ref.update({
                "owned_weight": new_weight,
                "units": current_units,
                "activeAt": int(datetime.now(timezone.utc).timestamp()),
            })

            txn_ref = db.reference(f"users/{uid}/transactions")
            txn_ref.update(updates["transactions"])

            print(f"  → owned_weight: {current_weight} → {new_weight}")
            print(f"  → units updated: {list(updates['skus_with_weight'].keys())}")
            print(f"  → transactions recorded: {list(updates['transactions'].keys())}")

            updated.append({"uid": uid, "email": email, "weight": new_weight})

        except Exception as e:
            print(f"  ❌ Firebase update error: {e}")
            errors.append({"uid": uid, "email": email, "error": str(e)})

    # ----------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print("PURCHASES IMPORT SUMMARY")
    print(f"{'=' * 50}")
    print(f"✅ Rows processed:  {processed_rows}")
    print(f"👤 Users updated:   {len(updated)}")
    print(f"⏭  Skipped:         {len(skipped)}")
    print(f"🚩 Red flags:       {len(red_flags)}")
    print(f"❌ Errors:          {len(errors)}")

    if red_flags:
        print("\n🚩 Red Flags (check data entry in SM):")
        for r in red_flags:
            print(f"  Row {r['row']} | txn={r['txn']} | {r['sku']} | {r['email']} | total=${r['total']}")

    if skipped:
        print("\nSkipped:")
        for s in skipped:
            print(f"  Row {s.get('row')} | txn={s.get('txn','')} | {s.get('sku','')} | {s.get('email','')} → {s.get('reason','')}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e['email']} → {e['error']}")


# ----------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Sales Master purchases into Firebase")
    parser.add_argument("--csv", required=True, help="Path to the ordered items CSV file")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"❌ File not found: {args.csv}")
        sys.exit(1)

    init_firebase()
    run_purchases(args.csv)

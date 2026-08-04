"""
SM-Importer Shared Utilities
==============================
Shared helpers used across sm_customers, sm_purchases,
update_ranks, and update_leaderboard. Import from here —
do NOT copy-paste these into individual scripts.
"""

import base64
import json
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

import firebase_admin
from firebase_admin import credentials, db


# ----------------------------------------------------------------
# FIREBASE
# ----------------------------------------------------------------

DATABASE_URL = "https://myezfirebase.firebaseio.com"


def init_firebase():
    """
    Initialize Firebase Admin SDK.
    No-op if already initialized — safe to call multiple times
    or from multiple modules in the same process.
    """
    try:
        firebase_admin.get_app()
        print("✅ Firebase already initialized\n")
        return
    except ValueError:
        pass  # Not yet initialized — proceed below

    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if key_json:
        key_dict = json.loads(base64.b64decode(key_json).decode("utf-8"))
        cred = credentials.Certificate(key_dict)
    else:
        cred = credentials.Certificate("security/firebase-service-account.json")

    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
    print("✅ Firebase initialized\n")


# ----------------------------------------------------------------
# SCORING
# ----------------------------------------------------------------

INFLATABLE_WEIGHT_THRESHOLD = 54  # lbs — items at or above this are inflatables


def is_inflatable(weight):
    """Returns True if the item weight qualifies as an inflatable."""
    return weight >= INFLATABLE_WEIGHT_THRESHOLD


def calculate_score(weight, total):
    """
    Calculate loyalty score for a single transaction.
      - Inflatable (weight >= 54 lbs): $5 = 1 point  →  int(total * 0.20)
      - Accessory  (weight <  54 lbs): $2 = 1 point  →  int(total * 0.50)
    """
    if is_inflatable(weight):
        return int(total * 0.20)
    return int(total * 0.50)


# ----------------------------------------------------------------
# SKU CLEANUP
# ----------------------------------------------------------------

# Known suffixes appended by Sales Master that are not part of the SKU.
# Add new variants here as they are discovered.
_SKU_STRIP_SUFFIXES = {"-TX", "-CA", "-FL"}


def clean_sku(sku):
    """Strip known Sales Master suffixes from a SKU (case-insensitive)."""
    upper = sku.upper()
    for suffix in _SKU_STRIP_SUFFIXES:
        if upper.endswith(suffix):
            return sku[: -len(suffix)]
    return sku


# ----------------------------------------------------------------
# EMAIL / DATE HELPERS
# ----------------------------------------------------------------

def clean_email(email_str):
    """
    Return the first valid email from a possibly multi-valued string.
    Handles comma- or semicolon-separated lists. Lowercases and validates.
    """
    if not email_str:
        return ""
    email = re.split(r"[,;]", email_str.strip())[0].strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return ""
    return email


def parse_date_to_unix(date_str):
    """
    Convert a date string to a UTC Unix timestamp (int).
    Accepts '%m/%d/%Y' and '%Y-%m-%d'. Falls back to now.
    """
    if not date_str:
        return int(datetime.now(timezone.utc).timestamp())
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return int(datetime.now(timezone.utc).timestamp())

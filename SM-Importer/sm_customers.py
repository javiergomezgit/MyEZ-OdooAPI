"""
Sales Master CSV Import Script — Phase 1
=========================================
Reads a CSV export from Sales Master and:
1. Skips rows with no email
2. Skips rows with no name
3. Creates Firebase Auth user silently (no email sent)
4. Writes full user profile to Firebase Realtime Database
5. Handles duplicates — skips if email already exists in Firebase Auth
6. Cleans phone numbers (digits only)
7. Lowercases emails

Usage:
    python3 sm_customers.py --csv path/to/clients.csv

Requirements:
    pip install firebase-admin python-dotenv requests --break-system-packages

Firebase Service Account:
    Set FIREBASE_SERVICE_ACCOUNT env var (base64-encoded JSON)
    OR place firebase-service-account.json in security/ folder
"""

import argparse
import base64
import csv
import json
import os
import re
import secrets
import string
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

import firebase_admin
from firebase_admin import auth, credentials, db


def init_firebase():
    """Initialize Firebase Admin SDK."""
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


PLACEHOLDER_IMAGE = (
    "https://firebasestorage.googleapis.com/v0/b/myezfirebase.appspot.com/o/"
    "myez-default-profile-image.png?alt=media&token=220f60c3-4cb2-480f-a365-f7852b229857"
)


def generate_temp_password(length=12):
    """Generate a random password — user never sees this in Phase 1."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def clean_phone(phone):
    """Strip all non-digit characters from phone number."""
    if not phone:
        return ""
    cleaned = re.sub(r"\D", "", phone.strip())
    return cleaned if cleaned not in ["0000000000", ""] else ""


def parse_date_to_unix(date_str):
    """Convert date string like '6/3/2026' to Unix timestamp float."""
    if not date_str:
        return datetime.now(timezone.utc).timestamp()
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        try:
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return datetime.now(timezone.utc).timestamp()


def email_exists_in_auth(email):
    """Check if a user with this email already exists in Firebase Auth."""
    try:
        auth.get_user_by_email(email)
        return True
    except auth.UserNotFoundError:
        return False
    except Exception as e:
        print(f"  ⚠ Auth lookup error for {email}: {e}")
        return False


def create_firebase_user(email, password):
    """Create Firebase Auth user. Returns (uid, error)."""
    try:
        user = auth.create_user(
            email=email,
            password=password,
            email_verified=False,
        )
        return user.uid, None
    except Exception as e:
        return None, str(e)


def write_firebase_profile(uid, data, check_only=False):
    """Write or check user profile in Firebase Realtime Database."""
    try:
        ref = db.reference(f"users/{uid}")
        if check_only:
            return ref.get()
        ref.set(data)
        return True
    except Exception as e:
        print(f"  ❌ Firebase DB error: {e}")
        return False


def clean_email(email_str):
    if not email_str:
        return ""
    # Handle multiple emails separated by comma or semicolon
    email = re.split(r"[,;]", email_str.strip())[0].strip().lower()
    # Validate basic email format
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return ""
    return email


def run_import(csv_path):
    print(f"📂 Reading: {csv_path}\n")

    processed = {}
    created = []
    skipped = []
    errors = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, start=1):
            name       = (row.get("Name") or "").strip()
            company    = (row.get("Company") or "").strip()
            phone      = clean_phone(row.get("Phone") or "")
            email      = clean_email(row.get("Email") or "")
            zip_code   = (row.get("BillToZipcode") or "").strip()
            created_on = (row.get("CreatedOn") or "").strip()
            sales_rep  = (row.get("UserName") or "").strip()

            print(f"[{i}] {name} | {email}")

            if not email:
                print(f"  ⚠ No email — skipping")
                skipped.append({"row": i, "name": name, "reason": "no email"})
                continue

            if not name:
                print(f"  ⚠ No name — skipping")
                skipped.append({"row": i, "email": email, "reason": "no name"})
                continue

            if email in processed:
                print(f"  → Duplicate in CSV — skipping")
                skipped.append({"row": i, "name": name, "email": email, "reason": "duplicate in CSV"})
                continue

            # If already exists in Firebase Auth — grab UID and check DB
            if email_exists_in_auth(email):
                existing_uid = auth.get_user_by_email(email).uid
                print(f"  → Already in Firebase Auth (uid={existing_uid})")
                existing_profile = write_firebase_profile(existing_uid, None, check_only=True)
                if existing_profile:
                    print(f"  → Already in Firebase DB — skipping")
                    skipped.append({"row": i, "name": name, "email": email, "reason": "already exists in Auth and DB"})
                    processed[email] = existing_uid
                else:
                    print(f"  → Not in Firebase DB — writing profile")
                    profile = {
                        "uid": existing_uid,
                        "name": name,
                        "email": email,
                        "phone": phone,
                        "zipCode": zip_code,
                        "company_name": company,
                        "salesRep": sales_rep,
                        "profile_image_url": PLACEHOLDER_IMAGE,
                        "owned_weight": 0,
                        "typeuser": "minimumweight",
                        "fcmTokens": {},
                        "subscribed": False,
                        "activeAt": int(datetime.now(timezone.utc).timestamp()),
                        "createdAt": int(parse_date_to_unix(created_on)),
                        "createdIn": "sm_manual",
                    }
                    success = write_firebase_profile(existing_uid, profile)
                    print(f"  → Firebase DB write: {'✅' if success else '❌'}")
                    processed[email] = existing_uid
                    created.append({"row": i, "name": name, "email": email, "uid": existing_uid})
                continue

            try:
                temp_password = generate_temp_password()
                uid, error = create_firebase_user(email, temp_password)

                if error:
                    print(f"  ❌ Auth creation failed: {error}")
                    errors.append({"row": i, "name": name, "email": email, "error": error})
                    continue

                print(f"  → Firebase Auth created (uid={uid})")

                profile = {
                    "uid": uid,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "zipCode": zip_code,
                    "company_name": company,
                    "salesRep": sales_rep,
                    "profile_image_url": PLACEHOLDER_IMAGE,
                    "owned_weight": 0,
                    "typeuser": "minimumweight",
                    "fcmTokens": {},
                    "subscribed": False,
                    "activeAt": int(datetime.now(timezone.utc).timestamp()),
                    "createdAt": parse_date_to_unix(created_on),
                    "createdIn": "sm_manual",
                }

                success = write_firebase_profile(uid, profile)
                print(f"  → Firebase DB write: {'✅' if success else '❌'}")

                processed[email] = uid
                created.append({"row": i, "name": name, "email": email, "uid": uid})

            except Exception as e:
                print(f"  ❌ Unexpected error: {e}")
                errors.append({"row": i, "name": name, "email": email, "error": str(e)})

    print("\n" + "=" * 50)
    print("IMPORT SUMMARY")
    print("=" * 50)
    print(f"✅ Created:  {len(created)}")
    print(f"⏭  Skipped:  {len(skipped)}")
    print(f"❌ Errors:   {len(errors)}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  Row {e['row']} | {e['name']} | {e['email']} → {e['error']}")

    if skipped:
        print("\nSkipped:")
        for s in skipped:
            print(f"  Row {s.get('row')} | {s.get('name','')} | {s.get('email','')} → {s.get('reason','')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Sales Master CSV into Firebase Auth + Realtime DB")
    parser.add_argument("--csv", required=True, help="Path to the Sales Master CSV file")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"❌ File not found: {args.csv}")
        sys.exit(1)

    init_firebase()
    run_import(args.csv)

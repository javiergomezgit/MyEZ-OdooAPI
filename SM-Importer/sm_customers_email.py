"""
Sales Master CSV Import Script — Phase 1 (with email notification)
===================================================================
Same as sm_customers.py but after creating each new Firebase Auth account
it sends the customer a password-setup email via Gmail OAuth2.

The email contains a Firebase password reset link so the customer can set
their own password and log in to the MyEZ app.

Usage:
    python3 sm_customers_email.py --csv path/to/clients.csv

Extra requirements (beyond sm_customers.py):
    pip install google-auth google-auth-oauthlib google-api-python-client

Gmail credentials must be in .env:
    GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_SENDER
    (run gmail_auth_setup.py once to populate these)
"""

import argparse
import base64
import csv
import os
import re
import secrets
import string
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

import firebase_admin
from firebase_admin import auth, db
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from utils import init_firebase, clean_email, parse_date_to_unix


# ----------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------

PLACEHOLDER_IMAGE = (
    "https://firebasestorage.googleapis.com/v0/b/myezfirebase.appspot.com/o/"
    "myez-default-profile-image.png?alt=media&token=220f60c3-4cb2-480f-a365-f7852b229857"
)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


# ----------------------------------------------------------------
# GMAIL SETUP
# ----------------------------------------------------------------

def build_gmail_service():
    """Build Gmail API service using stored OAuth2 refresh token."""
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
        client_id=os.getenv("GMAIL_CLIENT_ID"),
        client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_welcome_email(gmail_service, to_email, to_name, reset_link):
    """Send a welcome + password-setup email to the new customer."""
    sender = os.getenv("GMAIL_SENDER", "javier@ezinflatables.com")
    first_name = to_name.split()[0] if to_name else "there"

    subject = "Welcome to MyEZ — Set Up Your Account"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background:#f2f2f7; margin:0; padding:0; }}
    .wrapper {{ max-width:560px; margin:40px auto; background:#fff;
                border-radius:16px; overflow:hidden;
                box-shadow:0 2px 16px rgba(0,0,0,0.08); }}
    .header {{ background:#fff; padding:28px 40px 20px; text-align:center;
               border-bottom:1px solid #f0f0f0; }}
    .logo-mark {{ display:inline-block; background:#e8272b; color:#fff;
                  font-size:13px; font-weight:700; letter-spacing:1px;
                  padding:5px 12px; border-radius:6px; margin-bottom:10px; }}
    .header h1 {{ color:#1c1c1e; margin:0; font-size:22px; font-weight:700; }}
    .body {{ padding:36px 40px; color:#1c1c1e; }}
    .body h2 {{ font-size:20px; margin:0 0 12px; }}
    .body p {{ font-size:15px; line-height:1.6; color:#444; margin:0 0 16px; }}
    .btn {{ display:block; width:fit-content; margin:28px auto;
            background:#e8272b; color:#fff !important; text-decoration:none;
            padding:14px 36px; border-radius:10px;
            font-size:15px; font-weight:600; text-align:center; }}
    .footer {{ padding:20px 40px; text-align:center;
               font-size:12px; color:#aaa; border-top:1px solid #f0f0f0; }}
    .note {{ background:#f9f9f9; border-radius:10px; padding:14px 18px;
             font-size:13px; color:#666; margin-top:8px; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <div class="logo-mark">MyEZ</div>
      <h1>EZ Inflatables</h1>
    </div>
    <div class="body">
      <h2>Welcome, {first_name}!</h2>
      <p>Your MyEZ account has been created. Click the button below to set your password and get access to your account.</p>
      <a class="btn" href="{reset_link}">Set Up My Password</a>
      <div class="note">
        This link expires in 24 hours. If you did not expect this email,
        you can safely ignore it — no account will be active until you set a password.
      </div>
    </div>
    <div class="footer">
      <a href="https://ezinflatables.com" style="color:#aaa;text-decoration:none;">EZ Inflatables</a><br/>
      Questions? Reply to this email or call your sales rep.
    </div>
  </div>
</body>
</html>
"""

    text_body = (
        f"Welcome to MyEZ, {first_name}!\n\n"
        f"Your account has been created. Set your password here:\n{reset_link}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"— EZ Inflatables"
    )

    msg = MIMEMultipart("alternative")
    msg["From"]    = f"EZ Inflatables <{sender}>"
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_string().encode("utf-8")).decode()
    gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()


# ----------------------------------------------------------------
# HELPERS (same as sm_customers.py)
# ----------------------------------------------------------------

def generate_temp_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def clean_phone(phone):
    if not phone:
        return ""
    cleaned = re.sub(r"\D", "", phone.strip())
    return cleaned if cleaned not in ["0000000000", ""] else ""


def email_exists_in_auth(email):
    try:
        auth.get_user_by_email(email)
        return True
    except auth.UserNotFoundError:
        return False
    except Exception as e:
        print(f"  ⚠ Auth lookup error for {email}: {e}")
        return False


def create_firebase_user(email, password):
    try:
        user = auth.create_user(email=email, password=password, email_verified=False)
        return user.uid, None
    except Exception as e:
        return None, str(e)


def write_firebase_profile(uid, data, check_only=False):
    try:
        ref = db.reference(f"users/{uid}")
        if check_only:
            return ref.get()
        ref.set(data)
        return True
    except Exception as e:
        print(f"  ❌ Firebase DB error: {e}")
        return False


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------

def run_import(csv_path):
    print(f"📂 Reading: {csv_path}\n")
    print("📧 Email notifications: ON\n")

    # Build Gmail service once — reused for every email
    try:
        gmail_service = build_gmail_service()
        print("✅ Gmail service ready\n")
    except Exception as e:
        print(f"❌ Gmail setup failed: {e}")
        print("   Run gmail_auth_setup.py first.\n")
        raise

    processed  = {}
    created    = []
    skipped    = []
    errors     = []
    email_sent = []
    email_fail = []

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

            # Already exists in Firebase Auth
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
                        "uid": existing_uid, "name": name, "email": email,
                        "phone": phone, "zipCode": zip_code,
                        "company_name": company, "salesRep": sales_rep,
                        "profile_image_url": PLACEHOLDER_IMAGE,
                        "owned_weight": 0, "typeuser": "minimumweight",
                        "fcmTokens": {}, "subscribed": False,
                        "activeAt": int(datetime.now(timezone.utc).timestamp()),
                        "createdAt": int(parse_date_to_unix(created_on)),
                        "createdIn": "sm_manual",
                    }
                    success = write_firebase_profile(existing_uid, profile)
                    print(f"  → Firebase DB write: {'✅' if success else '❌'}")
                    processed[email] = existing_uid
                    created.append({"row": i, "name": name, "email": email, "uid": existing_uid})
                continue

            # Create new user
            try:
                temp_password = generate_temp_password()
                uid, error = create_firebase_user(email, temp_password)

                if error:
                    print(f"  ❌ Auth creation failed: {error}")
                    errors.append({"row": i, "name": name, "email": email, "error": error})
                    continue

                print(f"  → Firebase Auth created (uid={uid})")

                profile = {
                    "uid": uid, "name": name, "email": email,
                    "phone": phone, "zipCode": zip_code,
                    "company_name": company, "salesRep": sales_rep,
                    "profile_image_url": PLACEHOLDER_IMAGE,
                    "owned_weight": 0, "typeuser": "minimumweight",
                    "fcmTokens": {}, "subscribed": False,
                    "activeAt": int(datetime.now(timezone.utc).timestamp()),
                    "createdAt": parse_date_to_unix(created_on),
                    "createdIn": "sm_manual",
                }

                success = write_firebase_profile(uid, profile)
                print(f"  → Firebase DB write: {'✅' if success else '❌'}")

                # Generate password reset link and send welcome email
                try:
                    reset_link = auth.generate_password_reset_link(email)
                    send_welcome_email(gmail_service, email, name, reset_link)
                    print(f"  → Welcome email sent ✅")
                    email_sent.append(email)
                except Exception as e:
                    print(f"  → Welcome email failed ⚠: {e}")
                    email_fail.append({"email": email, "error": str(e)})

                processed[email] = uid
                created.append({"row": i, "name": name, "email": email, "uid": uid})

            except Exception as e:
                print(f"  ❌ Unexpected error: {e}")
                errors.append({"row": i, "name": name, "email": email, "error": str(e)})

    # ----------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------
    print("\n" + "=" * 50)
    print("IMPORT SUMMARY (with email)")
    print("=" * 50)
    print(f"✅ Created:       {len(created)}")
    print(f"📧 Emails sent:   {len(email_sent)}")
    print(f"⚠  Email failed:  {len(email_fail)}")
    print(f"⏭  Skipped:       {len(skipped)}")
    print(f"❌ Errors:        {len(errors)}")

    if email_fail:
        print("\nEmail failures (account created, email not sent):")
        for f in email_fail:
            print(f"  {f['email']} → {f['error']}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  Row {e['row']} | {e['name']} | {e['email']} → {e['error']}")

    if skipped:
        print("\nSkipped:")
        for s in skipped:
            print(f"  Row {s.get('row')} | {s.get('name','')} | {s.get('email','')} → {s.get('reason','')}")

    return {
        "created":     len(created),
        "skipped":     len(skipped),
        "errors":      len(errors),
        "email_sent":  len(email_sent),
        "email_fail":  len(email_fail),
        "error_list":  errors,
        "email_fail_list": email_fail,
    }


# ----------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import Sales Master CSV into Firebase + send welcome emails"
    )
    parser.add_argument("--csv", required=True, help="Path to the Sales Master CSV file")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"❌ File not found: {args.csv}")
        sys.exit(1)

    init_firebase()
    run_import(args.csv)

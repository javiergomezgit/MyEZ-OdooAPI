"""
Send "Set Up Your Password" emails to existing customers.
=========================================================
Reads a CSV with email, name, company columns and sends each customer
a Firebase password reset link framed as account setup (not a reset).

Usage:
    python3 send_welcome_emails.py --csv path/to/list.csv

CSV columns (case-insensitive):
    email        — required
    name         — optional, used for greeting
    company      — optional, shown in email

Must be run from the SM-Importer folder.
"""

import argparse
import base64
import csv
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

from firebase_admin import auth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from utils import init_firebase, clean_email

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def build_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
        client_id=os.getenv("GMAIL_CLIENT_ID"),
        client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_setup_email(gmail_service, to_email, to_name, company, reset_link):
    sender     = os.getenv("GMAIL_SENDER", "javier@ezinflatables.com")
    first_name = to_name.split()[0] if to_name else "there"

    subject = "Set Up Your MyEZ Account"

    company_line = f"<p style='font-size:14px;color:#666;margin:0 0 16px;'>{company}</p>" if company else ""

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
    .body h2 {{ font-size:20px; margin:0 0 8px; }}
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
      <h2>Hi {first_name}!</h2>
      {company_line}
      <p>Your MyEZ loyalty account is ready. Click below to set up your password and start tracking your points and exclusive deals.</p>
      <a class="btn" href="{reset_link}">Set Up My Account</a>
      <div class="note">
        This link expires in 24 hours. If you have any questions, reply to this email or reach out to your sales rep.
      </div>
    </div>
    <div class="footer">
      <a href="https://ezinflatables.com" style="color:#aaa;text-decoration:none;">EZ Inflatables</a><br/>
    </div>
  </div>
</body>
</html>
"""

    text_body = (
        f"Hi {first_name},\n\n"
        f"Your MyEZ loyalty account is ready. Set up your password here:\n{reset_link}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"— EZ Inflatables"
    )

    msg = MIMEMultipart("alternative")
    msg["From"]    = f"EZ Inflatables <{sender}>"
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_string().encode("utf-8")).decode()
    gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute()


def run(csv_path):
    print(f"📂 Reading: {csv_path}\n")

    init_firebase()

    try:
        gmail_service = build_gmail_service()
        print("✅ Gmail service ready\n")
    except Exception as e:
        print(f"❌ Gmail setup failed: {e}")
        sys.exit(1)

    sent    = []
    skipped = []
    errors  = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # Normalize column names to lowercase for flexible matching
        rows = list(reader)

    for i, row in enumerate(rows, start=1):
        # Case-insensitive column lookup
        normalized = {k.strip().lower(): v for k, v in row.items()}
        email   = clean_email(normalized.get("email", ""))
        name    = (normalized.get("name", "") or "").strip()
        company = (normalized.get("company", "") or normalized.get("company name", "") or "").strip()

        print(f"[{i}] {name or '(no name)'} | {email}")

        if not email:
            print(f"  ⚠ No email — skipping")
            skipped.append({"row": i, "name": name, "reason": "no email"})
            continue

        # Verify the user exists in Firebase Auth
        try:
            auth.get_user_by_email(email)
        except auth.UserNotFoundError:
            print(f"  ⚠ Not found in Firebase Auth — skipping")
            skipped.append({"row": i, "email": email, "name": name, "reason": "not in Firebase Auth"})
            continue
        except Exception as e:
            print(f"  ⚠ Auth lookup error: {e} — skipping")
            skipped.append({"row": i, "email": email, "name": name, "reason": str(e)})
            continue

        # Generate reset link and send
        try:
            reset_link = auth.generate_password_reset_link(email)
            send_setup_email(gmail_service, email, name, company, reset_link)
            print(f"  → ✅ Email sent")
            sent.append({"row": i, "email": email, "name": name})
        except Exception as e:
            print(f"  → ❌ Failed: {e}")
            errors.append({"row": i, "email": email, "name": name, "error": str(e)})

    # ----------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------
    print("\n" + "=" * 50)
    print("EMAIL SEND SUMMARY")
    print("=" * 50)
    print(f"📧 Sent:     {len(sent)}")
    print(f"⏭  Skipped:  {len(skipped)}")
    print(f"❌ Errors:   {len(errors)}")

    if skipped:
        print("\nSkipped:")
        for s in skipped:
            print(f"  Row {s['row']} | {s.get('name','')} | {s.get('email','')} → {s['reason']}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  Row {e['row']} | {e.get('name','')} | {e['email']} → {e['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send account setup emails to existing customers")
    parser.add_argument("--csv", required=True, help="Path to CSV file with email, name, company columns")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"❌ File not found: {args.csv}")
        sys.exit(1)

    run(args.csv)

"""
One-time Gmail OAuth2 setup.
Run this once — it opens a browser, you sign in with javier@ezinflatables.com,
and it saves the refresh token to your .env file automatically.

Usage:
    python3 gmail_auth_setup.py
"""

import os
import json

from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv, set_key

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Resolve credentials relative to repo root
script_dir  = os.path.dirname(os.path.abspath(__file__))
repo_root   = os.path.dirname(script_dir)
creds_path  = os.path.join(repo_root, "security", "gmail-oauth-credentials.json")
env_path    = os.path.join(script_dir, ".env")

if not os.path.exists(creds_path):
    print(f"❌ Credentials file not found: {creds_path}")
    raise SystemExit(1)

print("🌐 Opening browser — sign in with javier@ezinflatables.com\n")

flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

# Save to .env
load_dotenv(env_path)
set_key(env_path, "GMAIL_REFRESH_TOKEN", creds.refresh_token)
set_key(env_path, "GMAIL_CLIENT_ID",     creds.client_id)
set_key(env_path, "GMAIL_CLIENT_SECRET", creds.client_secret)
set_key(env_path, "GMAIL_SENDER",        "javier@ezinflatables.com")

print("\n✅ Gmail OAuth2 configured — tokens saved to .env")
print("   You won't need to run this again.")

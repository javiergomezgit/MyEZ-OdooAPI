"""
Dropbox Image Map Script — Phase 1
====================================
Lists all SKU folders in the Dropbox shared folder,
finds the first image in each {SKU}/{SKU}-PNG/ subfolder,
creates a shared link for it, and stores the URL in Firebase
at product_images/{SKU}.

Firebase structure:
  product_images/
    BB1582: "https://www.dropbox.com/scl/..."
    WS1430: "https://www.dropbox.com/scl/..."

Usage:
    python3 dropbox_image_map.py

Requirements:
    pip install requests firebase-admin python-dotenv --break-system-packages
"""

import base64
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

import requests
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
# DROPBOX HELPERS
# ----------------------------------------------------------------

ROOT_FOLDER = "/MainImages (1)"

def get_dropbox_token():
    """Return valid Dropbox access token, refreshing if expired."""
    token      = os.getenv("DROPBOX_TOKEN")
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")
    app_key    = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")

    test = requests.post(
        "https://api.dropboxapi.com/2/users/get_current_account",
        headers={"Authorization": f"Bearer {token}"}
    )
    if test.status_code == 200:
        return token

    resp = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        auth=(app_key, app_secret),
        data={"refresh_token": refresh_token, "grant_type": "refresh_token"}
    )
    new_token = resp.json().get("access_token")
    print(f"  → Token refreshed")
    return new_token


def list_folder(token, path):
    """List contents of a Dropbox folder."""
    resp = requests.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={"path": path, "recursive": False}
    )
    if resp.status_code != 200:
        print(f"  ❌ list_folder failed for {path}: {resp.text}")
        return []
    return resp.json().get("entries", [])


def get_or_create_shared_link(token, path):
    """Get existing shared link or create a new one for a file."""
    # Try to create
    resp = requests.post(
        "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={"path": path, "settings": {"requested_visibility": "public"}}
    )

    if resp.status_code == 200:
        url = resp.json().get("url", "")
        return url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "").replace("&dl=0", "")

    # If already exists fetch it
    if resp.status_code == 409:
        existing = requests.post(
            "https://api.dropboxapi.com/2/sharing/list_shared_links",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"path": path, "direct_only": True}
        )
        links = existing.json().get("links", [])
        if links:
            url = links[0].get("url", "")
            return url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "").replace("&dl=0", "")

    print(f"  ❌ Could not get shared link for {path}: {resp.text}")
    return None


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------

def run_image_map():
    print("📂 Connecting to Dropbox...\n")
    token = get_dropbox_token()

    # List all SKU folders in root
    sku_folders = list_folder(token, ROOT_FOLDER)
    sku_folders = [e for e in sku_folders if e[".tag"] == "folder"]
    print(f"Found {len(sku_folders)} SKU folders\n")

    image_map = {}
    success = 0
    failed  = 0

    for folder in sku_folders:
        sku  = folder["name"]
        path = folder["path_lower"]

        print(f"[{sku}]")

        # Look for {SKU}-PNG subfolder
        png_folder_path = f"{path}/{sku}-PNG"
        files = list_folder(token, png_folder_path)

        if not files:
            # Try lowercase
            png_folder_path = f"{path}/{sku.lower()}-png"
            files = list_folder(token, png_folder_path)

        # Filter to files only
        image_files = [f for f in files if f[".tag"] == "file"]

        if not image_files:
            print(f"  ⚠ No images found in {png_folder_path}")
            failed += 1
            continue

        # Take first image
        first_image = image_files[0]
        image_path  = first_image["path_lower"]
        print(f"  → First image: {first_image['name']}")

        # Get shared link
        url = get_or_create_shared_link(token, image_path)
        if url:
            image_map[sku] = url
            print(f"  → URL: {url[:60]}...")
            success += 1
        else:
            failed += 1

    # ----------------------------------------------------------------
    # WRITE TO FIREBASE
    # ----------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print("WRITING TO FIREBASE")
    print(f"{'=' * 50}\n")

    if image_map:
        ref = db.reference("product_images")
        ref.set(image_map)
        print(f"✅ Written {len(image_map)} image URLs to product_images/")
    else:
        print("❌ No images to write")

    # ----------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------
    print(f"\n{'=' * 50}")
    print("IMAGE MAP SUMMARY")
    print(f"{'=' * 50}")
    print(f"✅ Mapped:  {success}")
    print(f"❌ Failed:  {failed}")
    print(f"📦 Total:   {len(sku_folders)}")


# ----------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------

if __name__ == "__main__":
    init_firebase()
    run_image_map()

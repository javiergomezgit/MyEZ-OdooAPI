import os
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")
FIREBASE_DB_URL = "https://myezfirebase.firebaseio.com"
SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET")

RANK_TIERS = [
    (2500, "Minimumweight"),
    (5000, "Flyweight"),
    (7500, "Bantamweight"),
    (10000, "Featherweight"),
    (12500, "Lightweight"),
    (15000, "Welterweight"),
    (17500, "Middleweight"),
    (20000, "Cruiserweight"),
    (float("inf"), "Heavyweight"),
]

import json
import urllib.request

from fastapi import APIRouter

from core.config import FIREBASE_DB_URL, ODOO_DB, ODOO_PASSWORD
from core.helpers import firebase_read, get_db_token, odoo_authenticate

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("/odoo")
def get_clients():
    """Returns a list of active customers from Odoo with name, email, and phone."""
    uid, models = odoo_authenticate()
    clients = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.partner", "search_read",
        [[["customer_rank", ">", 0]]],
        {"fields": ["name", "email", "phone"], "limit": 5},
    )
    return {"clients": clients}


@router.get("/odoo/ranking")
def get_client_ranking():
    """Returns clients ranked by inflatable weight owned."""
    uid, models = odoo_authenticate()
    clients = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.partner", "search_read",
        [[["customer_rank", ">", 0]]],
        {"fields": ["name", "x_studio_rank_weight"], "limit": 30},
    )
    result = [
        {
            "id": c["id"],
            "name": c["name"],
            "rank_weight": (
                c["x_studio_rank_weight"]
                if c["x_studio_rank_weight"] not in [False, None, ""]
                else "No Rank Yet"
            ),
        }
        for c in clients
    ]
    return {"clients": result}


@router.get("/owned-units/{partner_id}")
def get_owned_units(partner_id: int):
    """Returns owned inflatable units, total weight, and rank tier for a specific customer from Firebase."""
    try:
        data = firebase_read(f"users/{partner_id}")
    except Exception:
        return {"success": False, "error": "Failed to fetch user data"}

    if not data:
        return {"success": False, "error": "User not found"}

    return {
        "success": True,
        "partner_id": partner_id,
        "owned_weight": data.get("owned_weight", 0),
        "rank": data.get("typeuser", "minimumweight"),
        "units": data.get("units", {}),
    }

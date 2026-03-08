from fastapi import FastAPI
from dotenv import load_dotenv
import xmlrpc.client
import os

load_dotenv()

app = FastAPI()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.get("/odoo/ping")
def odoo_ping():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    return {"odoo_uid": uid}

@app.get("/odoo/clients")
def get_clients():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})

    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    clients = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'res.partner', 'search_read',
        [[['customer_rank', '>', 0]]],
        {'fields': ['name', 'email', 'phone'], 'limit': 5}
        )
    return {"clients": clients}

@app.get("/odoo/clients/ranking")
def get_client_ranking():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    clients = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'res.partner', 'search_read',
        [[['customer_rank', '>', 0]]],
        {'fields': ['name', 'x_studio_rank_weight'], 'limit': 30}
    )
    result = [
        {
            "id": c["id"],
            "name": c["name"],
            "rank_weight": c["x_studio_rank_weight"] if c["x_studio_rank_weight"] not in [False, None, ""] else "No Rank Yet"
        }
        for c in clients
    ]
    return {"clients": result}

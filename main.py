from fastapi import FastAPI

from core.helpers import odoo_authenticate
from routers import clients, gamification, notifications, products, shopify

app = FastAPI(title="MyEZ Odoo API")

# ----------------------------------------------------------------
# ROUTERS
# ----------------------------------------------------------------
app.include_router(shopify.router)
app.include_router(clients.router)
app.include_router(products.router)
app.include_router(notifications.router)
app.include_router(gamification.router)


# ----------------------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------------------

@app.get("/ping")
def ping():
    """Health check — confirms the API is live."""
    return {"status": "ok"}


@app.get("/odoo/ping")
def odoo_ping():
    """Odoo auth check — confirms XML-RPC connection to Odoo is working."""
    uid, _ = odoo_authenticate()
    return {"odoo_uid": uid}


# ----------------------------------------------------------------
# FUTURE — AUTH
# POST /auth/login   — email + password → returns user profile + session
# POST /auth/signup  — name + email + password → creates Odoo user
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# FUTURE — ORDERS
# GET /orders/{partner_id}            — order history from Odoo
# GET /orders/{partner_id}/{order_id} — single order detail
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# FUTURE — CART / CHECKOUT
# POST /cart/add     — add product to cart
# POST /cart/remove  — remove product from cart
# POST /checkout     — submit order to Odoo
# ----------------------------------------------------------------

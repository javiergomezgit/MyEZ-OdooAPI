import json

from fastapi import APIRouter, HTTPException, Request

from core.config import ODOO_DB, ODOO_PASSWORD
from core.helpers import (
    firebase_write,
    generate_temp_password,
    odoo_authenticate,
    verify_shopify_webhook,
)

router = APIRouter(prefix="/shopify", tags=["Shopify"])


@router.post("/customer-created")
async def shopify_customer_created(request: Request):
    """
    Shopify webhook — fires when a new customer registers on the Shopify store.
    Flow:
      1. Verify Shopify HMAC signature
      2. Extract customer fields
      3. Create res.partner + res.users (portal) in Odoo
      4. Write user entry to Firebase
      5. Send welcome email with temp password via Odoo
    """
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not verify_shopify_webhook(body, hmac_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    data = json.loads(body)

    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    email = data.get("email", "")
    phone = data.get("phone", "") or ""
    zip_code = ""
    address = data.get("default_address")
    if address:
        zip_code = address.get("zip", "") or ""

    if not email:
        raise HTTPException(status_code=400, detail="No email in Shopify payload")

    temp_password = generate_temp_password()
    uid, models = odoo_authenticate()

    # Create Odoo partner
    partner_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.partner", "create", [{
            "name": full_name,
            "email": email,
            "phone": phone,
            "zip": zip_code,
            "company_id": 25,
            "customer_rank": 1,
        }]
    )


    # Create Odoo portal user
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.users", "create", [{
            "name": full_name,
            "login": email,
            "email": email,
            "password": temp_password,
            "partner_id": partner_id,
            "company_id": 25,
            "company_ids": [[6, 0, [25]]],
            "share": True,
        }]
    )

    # Write to Firebase
    firebase_write(f"users/{partner_id}", {
        "name": full_name,
        "email": email,
        "phone": phone,
        "zip": zip_code,
        "partner_id": partner_id,
        "typeuser": "portal",
        "owned_weight": 0,
    })

    # Send welcome email via Odoo
    mail_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "mail.mail", "create", [{
            "subject": "Welcome to EZ Inflatables",
            "body_html": f"""
                <p>Hi {first_name},</p>
                <p>Your EZ Inflatables account has been created.</p>
                <p><strong>Email:</strong> {email}<br/>
                <strong>Temporary password:</strong> {temp_password}</p>
                <p>Please log in and change your password as soon as possible.</p>
                <p>EZ Inflatables Team</p>
            """,
            "email_to": email,
            "auto_delete": True,
        }]
    )
    try:
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, "mail.mail", "send", [[mail_id]])
    except Exception:
        pass

    return {"status": "ok", "partner_id": partner_id, "email": email}

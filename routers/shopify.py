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
    Phase 2: add welcome email with temp password
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

    # Fallback: if no name provided, derive from email
    if not full_name:
        full_name = email.split("@")[0] if email else "Unknown"

    phone = data.get("phone", "") or ""
    zip_code = ""
    address = data.get("default_address")
    if address:
        zip_code = address.get("zip", "") or ""

    subscribed = data.get("accepts_marketing", False)
    created_at = data.get("created_at", "")

    if not email:
        raise HTTPException(status_code=400, detail="No email in Shopify payload")

    temp_password = generate_temp_password()

    # Authenticate Odoo before duplicate check
    uid, models = odoo_authenticate()

    # Check if user already exists in Odoo
    existing = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.users", "search",
        [[["login", "=", email]]]
    )
    if existing:
        return {"status": "skipped", "reason": "user already exists", "email": email}

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
    user_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "res.users", "create", [{
            "name": full_name,
            "login": email,
            "email": email,
            "password": temp_password,
            "partner_id": partner_id,
            "company_id": 25,
            "company_ids": [[6, 0, [25]]],
            "group_ids": [[6, 0, [10]]],
        }]
    )

    # Write to Firebase
    firebase_write(f"users/{partner_id}", {
        "uid": user_id,
        "partner_id": partner_id,
        "name": full_name,
        "email": email,
        "phone": phone,
        "zipCode": zip_code,
        "company_name": "",
        "profile_image_url": "https://firebasestorage.googleapis.com/v0/b/myezfirebase.appspot.com/o/myez-default-profile-image.png?alt=media&token=220f60c3-4cb2-480f-a365-f7852b229857",
        "owned_weight": 0,
        "units": {},
        "typeuser": "minimumweight",
        "fcmToken": "",
        "subscribed": subscribed,
        "completedSigningUp": False,
        "createdAt": created_at,
        "createdIn": "shopify",
    })

    # Phase 2: welcome email with temp password
    # mail_id = models.execute_kw(
    #     ODOO_DB, uid, ODOO_PASSWORD,
    #     "mail.mail", "create", [{
    #         "subject": "Welcome to EZ Inflatables",
    #         "body_html": f"""
    #             <p>Hi {first_name},</p>
    #             <p>Your EZ Inflatables account has been created.</p>
    #             <p><strong>Email:</strong> {email}<br/>
    #             <strong>Temporary password:</strong> {temp_password}</p>
    #             <p>Please log in and change your password as soon as possible.</p>
    #             <p>EZ Inflatables Team</p>
    #         """,
    #         "email_to": email,
    #         "auto_delete": True,
    #     }]
    # )
    # try:
    #     models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, "mail.mail", "send", [[mail_id]])
    # except Exception:
    #     pass

    return {"status": "ok", "partner_id": partner_id, "uid": user_id, "email": email}

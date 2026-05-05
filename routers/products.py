import requests
from fastapi import APIRouter

from core.config import ODOO_DB, ODOO_PASSWORD, ODOO_URL
from core.helpers import get_dropbox_token, odoo_authenticate

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("")
def get_products():
    """Returns published products from Odoo shop with name, price, category, and image URL."""
    uid, models = odoo_authenticate()
    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "product.template", "search_read",
        [[["is_published", "=", True], ["sale_ok", "=", True]]],
        {"fields": ["name", "list_price", "description_sale", "categ_id", "image_1920"], "limit": 50},
    )
    result = [
        {
            "id": p["id"],
            "name": p["name"],
            "price": p["list_price"],
            "description": p["description_sale"] or "",
            "category": p["categ_id"][1] if p["categ_id"] else "Uncategorized",
            "image_url": f"{ODOO_URL}/web/image/product.template/{p['id']}/image_1920",
        }
        for p in products
    ]
    return {"products": result}


@router.get("/{product_id}")
def get_product(product_id: int):
    """Returns full details for a single product by ID."""
    uid, models = odoo_authenticate()
    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        "product.template", "search_read",
        [[["id", "=", product_id]]],
        {"fields": ["name", "list_price", "description_sale", "categ_id", "image_1920"]},
    )
    if not products:
        return {"success": False, "error": "Product not found"}
    p = products[0]
    return {
        "success": True,
        "id": p["id"],
        "name": p["name"],
        "price": p["list_price"],
        "description": p["description_sale"] or "",
        "category": p["categ_id"][1] if p["categ_id"] else "Uncategorized",
        "image_url": f"{ODOO_URL}/web/image/product.template/{p['id']}/image_1920",
    }


@router.get("/image/{sku}")
def get_product_image(sku: str):
    """Returns a Dropbox shared folder URL for the given SKU's image folder."""
    token = get_dropbox_token()
    if not token:
        return {"error": "Dropbox token not configured"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    folder_path = f"/MainImages (1)/{sku}/{sku}-PNG"

    link_resp = requests.post(
        "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings",
        headers=headers,
        json={"path": folder_path},
    )

    if link_resp.status_code == 409:
        existing_resp = requests.post(
            "https://api.dropboxapi.com/2/sharing/list_shared_links",
            headers=headers,
            json={"path": folder_path, "direct_only": True},
        )
        links = existing_resp.json().get("links", [])
        if links:
            return {"url": links[0]["url"], "sku": sku}
        return {"error": "Could not retrieve shared link", "sku": sku}

    if link_resp.status_code != 200:
        return {"error": "Folder not found", "sku": sku}

    return {"url": link_resp.json().get("url"), "sku": sku}

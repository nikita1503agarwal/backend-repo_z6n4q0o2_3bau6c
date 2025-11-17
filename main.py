import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Multi-vendor E-commerce API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Helpers
# -----------------------------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")

class VendorIn(BaseModel):
    name: str
    description: Optional[str] = None
    email: str

class ProductIn(BaseModel):
    vendor_id: str
    title: str
    description: Optional[str] = None
    price: float
    stock: int
    category: Optional[str] = None
    images: Optional[List[str]] = None

class OrderItemIn(BaseModel):
    product_id: str
    quantity: int

class OrderIn(BaseModel):
    buyer_email: str
    items: List[OrderItemIn]

# -----------------------------
# Basic routes
# -----------------------------

@app.get("/")
def read_root():
    return {"message": "Multi-vendor E-commerce Backend is running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# -----------------------------
# Vendors
# -----------------------------

@app.post("/vendors")
def create_vendor(payload: VendorIn):
    vid = create_document("vendor", payload.model_dump())
    return {"id": vid}

@app.get("/vendors")
def list_vendors():
    vendors = get_documents("vendor")
    for v in vendors:
        v["id"] = str(v.pop("_id"))
    return vendors

# -----------------------------
# Products
# -----------------------------

@app.post("/products")
def create_product(payload: ProductIn):
    # Verify vendor exists
    vendor = db["vendor"].find_one({"_id": oid(payload.vendor_id)})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    pid = create_document("catalogproduct", payload.model_dump())
    return {"id": pid}

@app.get("/products")
def list_products(vendor_id: Optional[str] = None, q: Optional[str] = None, category: Optional[str] = None):
    query = {}
    if vendor_id:
        query["vendor_id"] = vendor_id
    if category:
        query["category"] = category
    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    products = list(db["catalogproduct"].find(query).limit(100))
    for p in products:
        p["id"] = str(p.pop("_id"))
    return products

@app.get("/products/{product_id}")
def get_product(product_id: str):
    p = db["catalogproduct"].find_one({"_id": oid(product_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    p["id"] = str(p.pop("_id"))
    return p

# -----------------------------
# Orders (multi-vendor)
# -----------------------------

@app.post("/orders")
def create_order(payload: OrderIn):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must have items")
    items = []
    total = 0.0
    for it in payload.items:
        prod = db["catalogproduct"].find_one({"_id": oid(it.product_id)})
        if not prod:
            raise HTTPException(status_code=404, detail=f"Product {it.product_id} not found")
        if int(prod.get("stock", 0)) < it.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {prod.get('title')}")
        line_total = float(prod.get("price", 0)) * it.quantity
        total += line_total
        items.append({
            "product_id": it.product_id,
            "quantity": it.quantity,
            "price": float(prod.get("price", 0)),
            "title": prod.get("title"),
            "vendor_id": prod.get("vendor_id")
        })
    order_doc = {
        "buyer_email": payload.buyer_email,
        "items": items,
        "total": round(total, 2),
        "status": "pending"
    }
    oid_str = create_document("order", order_doc)
    return {"id": oid_str, "total": round(total, 2), "status": "pending"}

@app.get("/orders")
def list_orders(buyer_email: Optional[str] = None):
    query = {"buyer_email": buyer_email} if buyer_email else {}
    orders = list(db["order"].find(query).sort("created_at", -1).limit(50))
    for o in orders:
        o["id"] = str(o.pop("_id"))
    return orders

# -----------------------------
# Schema endpoint for viewer (kept)
# -----------------------------

from schemas import User, Product, Vendor, CatalogProduct, Order, OrderItem

@app.get("/schema")
def get_schema():
    return {
        "user": User.model_json_schema(),
        "product": Product.model_json_schema(),
        "vendor": Vendor.model_json_schema(),
        "catalogproduct": CatalogProduct.model_json_schema(),
        "order": Order.model_json_schema(),
        "orderitem": OrderItem.model_json_schema(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

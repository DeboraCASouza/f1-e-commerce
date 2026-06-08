import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = "HS256"
SERVICE_SECRET = os.getenv("SERVICE_SECRET", "service-secret")
DB_FILE = os.getenv("DB_FILE", "data/products.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

security = HTTPBearer()
app = FastAPI(title="Products Service")


@contextmanager
def get_db():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            category TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class ProductCreate(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    price: float
    stock: int = 0
    category: str = ""


class StockUpdate(BaseModel):
    delta: int


def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products/categories")
def list_categories():
    with get_db() as db:
        rows = db.execute(
            "SELECT DISTINCT category FROM products WHERE category != '' ORDER BY category"
        ).fetchall()
    return [r["category"] for r in rows]


@app.get("/products")
def list_products(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    sql = "SELECT * FROM products WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if category:
        sql += " AND category = ?"
        params.append(category)

    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
        rows = db.execute(
            sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, (page - 1) * limit],
        ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
    }


@app.get("/products/{product_id}")
def get_product(product_id: str):
    with get_db() as db:
        row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return dict(row)


@app.post("/products", status_code=201)
def create_product(req: ProductCreate, _: dict = Depends(verify_admin)):
    if req.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0")
    if req.stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")

    product = {
        "id": req.id or str(uuid.uuid4()),
        "name": req.name.strip(),
        "description": req.description.strip(),
        "price": req.price,
        "stock": req.stock,
        "category": req.category.strip(),
        "created_at": datetime.utcnow().isoformat(),
    }
    with get_db() as db:
        db.execute(
            "INSERT INTO products (id, name, description, price, stock, category, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuple(product.values()),
        )
    logger.info(f"Product created: {product['name']} [{product['id']}]")
    return product


@app.patch("/products/{product_id}/stock")
def update_stock(
    product_id: str,
    req: StockUpdate,
    x_service_secret: Optional[str] = Header(None),
):
    if x_service_secret != SERVICE_SECRET:
        raise HTTPException(status_code=403, detail="Invalid service secret")

    with get_db() as db:
        if req.delta < 0:
            result = db.execute(
                "UPDATE products SET stock = stock + ? WHERE id = ? AND stock >= ?",
                (req.delta, product_id, -req.delta),
            )
            if result.rowcount == 0:
                row = db.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Product not found")
                raise HTTPException(status_code=409, detail=f"Insufficient stock (available: {row['stock']})")
        else:
            result = db.execute(
                "UPDATE products SET stock = stock + ? WHERE id = ?",
                (req.delta, product_id),
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Product not found")

    logger.info(f"Stock updated: product={product_id} delta={req.delta}")
    return {"ok": True}

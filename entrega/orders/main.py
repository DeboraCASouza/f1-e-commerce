import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = "HS256"
SERVICE_SECRET = os.getenv("SERVICE_SECRET", "service-secret")
PRODUCTS_URL = os.getenv("PRODUCTS_URL", "http://localhost:8000")
DB_FILE = os.getenv("DB_FILE", "data/orders.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

security = HTTPBearer()
app = FastAPI(title="Orders Service")

VALID_TRANSITIONS = {
    "pending":   {"confirmed", "cancelled"},
    "confirmed": {"shipped",   "cancelled"},
    "shipped":   {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}
RESTORE_STOCK_FROM = {"pending", "confirmed"}


@contextmanager
def get_db():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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


class OrderCreate(BaseModel):
    product_id: str
    quantity: int = 1


class StatusUpdate(BaseModel):
    status: str


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = verify_token(credentials)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


async def patch_stock(product_id: str, delta: int):
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.patch(
            f"{PRODUCTS_URL}/products/{product_id}/stock",
            json={"delta": delta},
            headers={"X-Service-Secret": SERVICE_SECRET},
            timeout=5.0,
        )
    if resp.status_code == 409:
        raise HTTPException(status_code=409, detail=resp.json().get("detail", "Insufficient stock"))
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Failed to update product stock")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/orders", status_code=201)
async def create_order(req: OrderCreate, token: dict = Depends(verify_token)):
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

    await patch_stock(req.product_id, -req.quantity)

    now = datetime.utcnow().isoformat()
    order_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO orders (id, user_id, product_id, quantity, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, token["userId"], req.product_id, req.quantity, "pending", now, now),
        )
    logger.info(f"Order created: {order_id} user={token['userId']}")
    return {"id": order_id, "user_id": token["userId"], "product_id": req.product_id,
            "quantity": req.quantity, "status": "pending", "created_at": now, "updated_at": now}


@app.get("/orders/all")
def get_all_orders(token: dict = Depends(verify_admin)):
    with get_db() as db:
        rows = db.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.get("/orders/{user_id}")
def get_user_orders(user_id: str, token: dict = Depends(verify_token)):
    if token["userId"] != user_id and token.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.patch("/orders/{order_id}/status")
async def update_status(order_id: str, req: StatusUpdate, token: dict = Depends(verify_token)):
    with get_db() as db:
        row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    order = dict(row)
    current, new_status = order["status"], req.status

    if token.get("role") != "admin":
        if order["user_id"] != token["userId"]:
            raise HTTPException(status_code=403, detail="Access denied")
        if new_status != "cancelled":
            raise HTTPException(status_code=403, detail="Users can only cancel orders")

    if new_status not in VALID_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=400, detail=f"Cannot transition '{current}' → '{new_status}'")

    if new_status == "cancelled" and current in RESTORE_STOCK_FROM:
        await patch_stock(order["product_id"], order["quantity"])

    now = datetime.utcnow().isoformat()
    with get_db() as db:
        db.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, order_id))

    logger.info(f"Order {order_id}: {current} → {new_status}")
    return {**order, "status": new_status, "updated_at": now}

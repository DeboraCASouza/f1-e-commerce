import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("gateway.log")],
)
logger = logging.getLogger(__name__)

SERVICES = {
    "users":      {"url": os.getenv("USERS_URL",      "http://localhost:5001"), "healthy": True, "failures": 0},
    "products_1": {"url": os.getenv("PRODUCTS_1_URL", "http://localhost:5002"), "healthy": True, "failures": 0},
    "products_2": {"url": os.getenv("PRODUCTS_2_URL", "http://localhost:5012"), "healthy": True, "failures": 0},
    "orders":     {"url": os.getenv("ORDERS_URL",     "http://localhost:5003"), "healthy": True, "failures": 0},
}

HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "5"))
_product_rr = 0


async def check_service(name: str, svc: dict):
    url = f"{svc['url']}/health"
    for attempt in range(2):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=2.0)
            if resp.status_code == 200:
                if not svc["healthy"]:
                    logger.info(f"Service '{name}' RECOVERED at {datetime.utcnow().isoformat()}")
                svc["healthy"] = True
                svc["failures"] = 0
                return
        except Exception:
            pass
        if attempt == 0:
            await asyncio.sleep(0.3)

    svc["failures"] += 1
    if svc["healthy"]:
        logger.error(f"Service '{name}' DOWN at {datetime.utcnow().isoformat()}")
    svc["healthy"] = False


async def heartbeat_loop():
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        await asyncio.gather(*[check_service(n, s) for n, s in SERVICES.items()])


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(heartbeat_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="API Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "index.html")
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

@app.get("/ui")
def serve_frontend():
    return FileResponse(FRONTEND)

@app.get("/static/{filepath:path}")
def serve_static(filepath: str):
    full = os.path.normpath(os.path.join(FRONTEND_DIR, filepath))
    if not full.startswith(os.path.normpath(FRONTEND_DIR)):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    if not os.path.isfile(full):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return FileResponse(full)


def _pick_replica():
    global _product_rr
    healthy = [s for k, s in SERVICES.items() if k.startswith("products_") and s["healthy"]]
    if not healthy:
        return None
    svc = healthy[_product_rr % len(healthy)]
    _product_rr += 1
    return svc


def _fwd_headers(request: Request) -> dict:
    return {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}


async def _proxy(request: Request, target_url: str) -> Response:
    body = await request.body()
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=_fwd_headers(request),
            content=body,
            params=dict(request.query_params),
            timeout=10.0,
        )
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json"))


@app.get("/health")
def gateway_health():
    return {"status": "ok", "services": {n: {"healthy": s["healthy"]} for n, s in SERVICES.items()}}


# ── Users ──────────────────────────────────────────────────────────────────────

@app.api_route("/users", methods=["GET", "POST"])
@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_users(request: Request, path: str = ""):
    svc = SERVICES["users"]
    if not svc["healthy"]:
        return JSONResponse({"detail": "Users service unavailable"}, status_code=503)
    suffix = f"/{path}" if path else ""
    return await _proxy(request, f"{svc['url']}/users{suffix}")


# ── Products — reads (round-robin) ────────────────────────────────────────────

@app.api_route("/products/categories", methods=["GET"])
@app.api_route("/products", methods=["GET"])
@app.api_route("/products/{path:path}", methods=["GET"])
async def proxy_products_read(request: Request, path: str = ""):
    replica = _pick_replica()
    if not replica:
        return JSONResponse({"detail": "Products service unavailable"}, status_code=503)
    suffix = f"/{path}" if path else ""
    return await _proxy(request, f"{replica['url']}/products{suffix}")


# ── Products — write (both replicas) ─────────────────────────────────────────

@app.post("/products")
async def proxy_products_write(request: Request):
    p1, p2 = SERVICES["products_1"], SERVICES["products_2"]
    if not p1["healthy"] or not p2["healthy"]:
        return JSONResponse({"detail": "Cannot write: a product replica is unavailable"}, status_code=503)

    body_bytes = await request.body()
    try:
        body_json = json.loads(body_bytes)
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    body_json["id"] = str(uuid.uuid4())
    modified = json.dumps(body_json).encode()
    headers = _fwd_headers(request)
    headers["content-type"] = "application/json"

    async with httpx.AsyncClient() as client:
        r1, r2 = await asyncio.gather(
            client.post(f"{p1['url']}/products", headers=headers, content=modified, timeout=10.0),
            client.post(f"{p2['url']}/products", headers=headers, content=modified, timeout=10.0),
        )

    if r1.status_code not in (200, 201) or r2.status_code not in (200, 201):
        logger.error(f"Product replication failed — r1={r1.status_code} r2={r2.status_code}")
        return JSONResponse({"detail": "Replication failed"}, status_code=500)

    return Response(content=r1.content, status_code=r1.status_code,
                    media_type=r1.headers.get("content-type", "application/json"))


# ── Products — stock update (both replicas, with rollback) ────────────────────

@app.patch("/products/{product_id}/stock")
async def proxy_stock_update(product_id: str, request: Request):
    p1, p2 = SERVICES["products_1"], SERVICES["products_2"]
    if not p1["healthy"] or not p2["healthy"]:
        return JSONResponse({"detail": "Cannot update stock: replica unavailable"}, status_code=503)

    body_bytes = await request.body()
    try:
        body_json = json.loads(body_bytes)
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    headers = _fwd_headers(request)
    headers["content-type"] = "application/json"

    async with httpx.AsyncClient() as client:
        r1, r2 = await asyncio.gather(
            client.patch(f"{p1['url']}/products/{product_id}/stock", headers=headers, content=body_bytes, timeout=10.0),
            client.patch(f"{p2['url']}/products/{product_id}/stock", headers=headers, content=body_bytes, timeout=10.0),
        )

    ok1, ok2 = r1.status_code in (200, 201), r2.status_code in (200, 201)
    if ok1 and ok2:
        return Response(content=r1.content, status_code=200, media_type="application/json")

    # Rollback whichever side succeeded
    rollback = json.dumps({"delta": -body_json["delta"]}).encode()
    async with httpx.AsyncClient() as client:
        if ok1 and not ok2:
            await client.patch(f"{p1['url']}/products/{product_id}/stock", headers=headers, content=rollback, timeout=5.0)
            return Response(content=r2.content, status_code=r2.status_code, media_type="application/json")
        if ok2 and not ok1:
            await client.patch(f"{p2['url']}/products/{product_id}/stock", headers=headers, content=rollback, timeout=5.0)
            return Response(content=r1.content, status_code=r1.status_code, media_type="application/json")

    return Response(content=r1.content, status_code=r1.status_code, media_type="application/json")


# ── Orders ─────────────────────────────────────────────────────────────────────

@app.api_route("/orders", methods=["GET", "POST"])
@app.api_route("/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_orders(request: Request, path: str = ""):
    svc = SERVICES["orders"]
    if not svc["healthy"]:
        return JSONResponse({"detail": "Orders service unavailable"}, status_code=503)
    suffix = f"/{path}" if path else ""
    return await _proxy(request, f"{svc['url']}/orders{suffix}")

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.responses import PlainTextResponse

from app.api.advanced_control import router as advanced_control_router
from app.api.ai_autopilot import router as ai_autopilot_router
from app.api.ai_config import router as ai_config_router
from app.api.client_manager import router as client_manager_router
from app.api.direct_configs import router as direct_configs_router
from app.api.inbounds import router as inbounds_router
from app.api.routes import router
from app.api.protocols import router as protocols_router
from app.api.subscription_server import public_router as subscription_public_router, router as subscription_router
from app.api.secure_subscription import public_router as secure_subscription_public_router
from app.api.ai_settings import router as ai_settings_router
from app.api.node_management import router as node_management_router
from app.api.xray_management import router as xray_management_router
from app.api.user_provisioning import router as user_provisioning_router
from app.core.config import settings
from app.db.base import SessionLocal
from app.services.auth import ensure_seed
from app.services.inbound_store import ensure_tables as ensure_inbound_tables
from app.services.rate_limit import enforce
from app.services.scheduler import start_scheduler, stop_scheduler

LEGACY_DISABLED_PREFIXES = (
    "/api/v1/plans", "/api/v1/routes", "/api/v1/experiments", "/api/v1/optimizer", "/api/v1/ai/configure-node",
)
PUBLIC_PRIVATE_PREFIXES = ("/s/", "/link/", "/subscriptions/")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db = SessionLocal()
    try:
        ensure_seed(db)
        ensure_inbound_tables(db.get_bind())
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, version=settings.app_version, openapi_version="3.1.0", docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Master-Secret"])


def _host_allowed(request: Request) -> bool:
    host = (request.headers.get("host") or "").split(":", 1)[0].strip().lower().rstrip(".")
    return host in {item.lower().rstrip(".") for item in settings.trusted_host_list} or host == "localhost" or host == "127.0.0.1"


def _is_legacy_username_link(path: str) -> bool:
    if not path.startswith("/link/"):
        return False
    parts = path.split("/")
    if len(parts) < 3 or not parts[2]:
        return False
    return len(parts[2]) < 40


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    path = request.url.path
    if not _host_allowed(request) and path not in {"/health", "/ready", "/api/v1/health"}:
        return PlainTextResponse("Invalid host header", status_code=400)
    if any(path == prefix or path.startswith(prefix + "/") for prefix in LEGACY_DISABLED_PREFIXES):
        return JSONResponse(status_code=404, content={"detail": "feature_removed"})
    if _is_legacy_username_link(path):
        return JSONResponse(status_code=404, content={"detail": "username_subscription_disabled"})
    if path not in {"/health", "/ready", "/api/v1/health", "/docs", "/redoc", "/openapi.json"}:
        try:
            enforce(request)
        except Exception as exc:
            return JSONResponse(status_code=getattr(exc, "status_code", 429), content={"detail": getattr(exc, "detail", "rate_limit_exceeded")})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith("/api/") or any(path.startswith(prefix) for prefix in PUBLIC_PRIVATE_PREFIXES):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    elif path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "public, max-age=60"
    return response


@app.get("/health", include_in_schema=False)
def root_health() -> dict:
    return {"ok": True, "service": settings.app_name, "version": settings.app_version}


@app.get("/ready", include_in_schema=False)
def readiness() -> Response:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse({"ok": True, "service": settings.app_name, "version": settings.app_version, "database": "ready"})
    except Exception:
        return JSONResponse(status_code=503, content={"ok": False, "service": settings.app_name, "database": "unavailable"})
    finally:
        db.close()


app.include_router(user_provisioning_router)
app.include_router(ai_settings_router)
app.include_router(ai_config_router)
app.include_router(ai_autopilot_router)
app.include_router(advanced_control_router)
app.include_router(subscription_router)
app.include_router(router)
app.include_router(protocols_router)
app.include_router(secure_subscription_public_router)
app.include_router(subscription_public_router)
app.include_router(node_management_router)
app.include_router(xray_management_router)
app.include_router(client_manager_router)
app.include_router(inbounds_router)
app.include_router(direct_configs_router)

STATIC = Path(__file__).parent / "static"
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets", check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def frontend() -> Response:
    if not (STATIC / "index.html").exists():
        return JSONResponse({"service": settings.app_name, "frontend": "build frontend/ and restart the master"})
    return FileResponse(STATIC / "index.html")

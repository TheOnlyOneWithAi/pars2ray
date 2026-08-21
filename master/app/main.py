from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.ai_config import router as ai_config_router
from app.api.routes import router
from app.api.ai_settings import router as ai_settings_router
from app.api.node_management import router as node_management_router
from app.core.config import settings
from app.db.base import SessionLocal
from app.services.auth import ensure_seed
from app.services.rate_limit import enforce
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    db = SessionLocal()
    try:
        ensure_seed(db)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, version=settings.app_version, openapi_version="3.1.0", docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json", lifespan=lifespan)

if settings.trusted_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Master-Secret"])


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.url.path not in {"/health", "/api/v1/health", "/docs", "/redoc", "/openapi.json"}:
        try:
            enforce(request)
        except Exception as exc:
            return JSONResponse(status_code=getattr(exc, "status_code", 429), content={"detail": getattr(exc, "detail", "rate_limit_exceeded")})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "public, max-age=60"
    return response


@app.get("/health", include_in_schema=False)
def root_health() -> dict:
    return {"ok": True, "service": settings.app_name, "version": settings.app_version}


app.include_router(ai_settings_router)
app.include_router(ai_config_router)
app.include_router(router)
app.include_router(node_management_router)

STATIC = Path(__file__).parent / "static"
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets", check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def frontend() -> Response:
    if not (STATIC / "index.html").exists():
        return JSONResponse({"service": settings.app_name, "frontend": "build frontend/ and restart the master"})
    return FileResponse(STATIC / "index.html")

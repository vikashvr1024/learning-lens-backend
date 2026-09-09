import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import router
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("student-diagnostics")

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Adaptive AI Student Diagnostics API",
    version=settings.app_version,
    description="Deterministic assessment analytics with validated AI-assisted remediation.",
    lifespan=lifespan,
)
allowed_origins = settings.frontend_origins
if settings.app_env != "production":
    allowed_origins = list(dict.fromkeys([
        *allowed_origins,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3100",
        "http://127.0.0.1:3100",
        "http://192.168.1.7:3100",
        "http://192.168.1.7:8000",
    ]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.trycloudflare\.com" if settings.app_env != "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"event": "request_failed", "request_id": request_id, "route": request.url.path}))
        raise
    latency = round((time.perf_counter() - started) * 1000, 2)
    response.headers["x-request-id"] = request_id
    logger.info(json.dumps({
        "event": "request_complete", "request_id": request_id,
        "route": request.url.path, "method": request.method,
        "status": response.status_code, "latency_ms": latency,
    }))
    return response


@app.get("/")
def root():
    return {
        "name": "Adaptive AI Student Diagnostics API",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    database = "ok"
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    # Always return 200 so Render's health check passes while the app is
    # alive; the `database` field reports DB readiness separately.
    status = "ok" if database == "ok" else "degraded"
    return JSONResponse(
        status_code=200,
        content={"status": status, "database": database, "version": settings.app_version},
    )

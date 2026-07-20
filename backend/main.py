"""
main.py
--------
Application entrypoint. Wires together middleware, routers, rate limiting,
and startup/shutdown hooks.

Run with:
    uvicorn main:app --reload --port 8000
"""
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api import admin, chat
from config.settings import get_settings
from database.session import db_session, init_db
from database.models import RequestLog

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.APP_NAME,
    description="RAG-powered customer support copilot for N+ONE DATACENTERS.",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS: only the official N+ONE site (and local dev) may call the API ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Security headers (defense in depth against clickjacking, MIME sniffing) ---
@app.middleware("http")
async def add_secure_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# --- Request logging middleware: every call is timed & persisted for the admin dashboard ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    request_id = str(uuid.uuid4())
    error_text = ""
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:  # noqa: BLE001 - we log then re-raise
        status_code = 500
        error_text = str(exc)
        logger.exception("Unhandled exception on {} [{}]", request.url.path, request_id)
        raise
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            with db_session() as db:
                db.add(
                    RequestLog(
                        endpoint=str(request.url.path),
                        status_code=locals().get("status_code", 500),
                        client_ip=request.client.host if request.client else "",
                        duration_ms=duration_ms,
                        error=error_text,
                    )
                )
        except Exception:
            logger.warning("Failed to persist request log (non-fatal)")
    return response


# --- Global error handler: never leak stack traces to the client ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: {}", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("{} started | env={} | llm_provider={}", settings.APP_NAME, settings.APP_ENV, settings.LLM_PROVIDER)


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


app.include_router(chat.router)
app.include_router(admin.router)

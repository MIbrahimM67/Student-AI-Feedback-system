"""
GradeWise v3 — FastAPI application entry point.

Wires up:
  - asyncpg pool (Postgres)
  - aioredis (cache)
  - ResilientLLM (DigitalOcean Gradient)
  - All API routers

Phase 0 endpoints:
  GET  /health         → {status, postgres, redis}
  POST /_debug/embed   → test Gradient embed end-to-end

Full routes added in later phases.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db.postgres import init_pool, close_pool, get_conn
from app.services.llm_provider import build_llm_from_env
from app.config import settings
from app.services.task_dispatch import start_worker, stop_worker
import asyncio

# ---- App state --------------------------------------------------------------
_redis = None
_llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _llm

    if settings.DOCUMENT_DEMO:
        if settings.USE_MOCKS or settings.DEBUG:
            raise RuntimeError("The public document demo requires USE_MOCKS=false and DEBUG=false.")
        if not settings.DEMO_ALLOWED_UIDS.strip():
            raise RuntimeError("Set DEMO_ALLOWED_UIDS to the invited Firebase user IDs.")
        if settings.DB_POOL_MAX_SIZE < 3:
            raise RuntimeError("The demo requires DB_POOL_MAX_SIZE >= 3.")
    await init_pool()
    if settings.DOCUMENT_DEMO:
        async with get_conn() as conn:
            await conn.execute("SELECT id FROM demo_jobs LIMIT 0")
            await conn.execute("SELECT id FROM demo_files LIMIT 0")
            if settings.INFERENCE_COOLDOWN_PERSISTENCE:
                await conn.execute("SELECT key_hash FROM provider_key_cooldowns LIMIT 0")

    if not settings.DOCUMENT_DEMO:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    _llm = build_llm_from_env()
    if settings.DOCUMENT_DEMO and settings.DEMO_VERIFY_PROVIDERS:
        from app.services.demo_verification import verify_demo_providers
        await verify_demo_providers()
    if settings.DOCUMENT_DEMO and settings.DEMO_VERIFY_CODE_RUNNER:
        from app.services.remote_code_runner import verify_runner
        await verify_runner()
    start_worker()
    keepalive_task = None
    if settings.DOCUMENT_DEMO and settings.DEMO_KEEPALIVE_ENABLED:
        from app.services.demo_keepalive import keepalive
        keepalive_task = asyncio.create_task(keepalive())

    try:
        yield
    finally:
        from app.services.demo_keepalive import stop_keepalive
        await stop_keepalive(keepalive_task)
        await stop_worker()
        await close_pool()
        if _redis:
            await _redis.aclose()


app = FastAPI(
    title=settings.APP_NAME,
    version="3.0.0",
    lifespan=lifespan,
)

frontend_origins = [settings.FRONTEND_URL.rstrip("/"), "https://student-ai-feedback-system.vercel.app", "http://localhost:3000", "http://127.0.0.1:3000"]
if settings.DOCUMENT_DEMO and settings.DEMO_PREVIEW_URL:
    frontend_origins.append(settings.DEMO_PREVIEW_URL.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount local uploads directory to serve files statically
if not settings.DOCUMENT_DEMO:
    os.makedirs("/app/uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="/app/uploads"), name="uploads")

from fastapi.responses import JSONResponse
from fastapi import Request
import traceback
import logging

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_details = traceback.format_exc()
    logger.error(f"Unhandled Exception: {error_details}")
    return JSONResponse(
        status_code=500,
        content=({"message": str(exc), "details": error_details}
                 if settings.DEBUG else {"message": "Internal server error"}),
    )


# ---- Dependency helpers (import these in route files) -----------------------

def get_redis():
    assert _redis is not None, "Redis not initialised"
    return _redis


def get_llm():
    assert _llm is not None, "LLM not initialised"
    return _llm


# ---- /health ----------------------------------------------------------------

@app.get("/ping", tags=["ops"])
async def ping():
    return {"status": "awake"}

@app.get("/health", tags=["ops"])
async def health() -> dict:
    pg_ok = "fail"
    redis_ok = "not_required" if settings.DOCUMENT_DEMO else "fail"
    try:
        async with get_conn() as conn:
            await conn.execute("SELECT 1")
        pg_ok = "ok"
    except Exception:
        pass
    if not settings.DOCUMENT_DEMO:
        try:
            r = get_redis()
            await r.ping()
            redis_ok = "ok"
        except Exception:
            pass

    from app.services.task_dispatch import worker_healthy
    overall = "ok" if pg_ok == "ok" and redis_ok in {"ok", "not_required"} and worker_healthy() else "degraded"
    result = {"status": overall, "postgres": pg_ok, "redis": redis_ok}
    if overall != "ok":
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/capabilities", tags=["ops"])
async def capabilities():
    from app.services.demo_limits import code_execution_available
    return {
        "document_demo": settings.DOCUMENT_DEMO,
        "code_execution": code_execution_available(),
        "batch_grading": True,
        "max_batch_files": min(30, settings.INSTRUCTOR_BATCH_MAX_FILES),
        "internal_similarity": True,
        "internal_similarity_method": "tfidf_and_word_trigrams" if settings.DOCUMENT_DEMO else "semantic",
        "knowledge_base": True,
        "knowledge_base_method": "full_text" if settings.DOCUMENT_DEMO else "semantic",
        "max_file_mb": settings.DEMO_MAX_FILE_MB if settings.DOCUMENT_DEMO else settings.STUDENT_MAX_FILE_MB,
    }


# ---- /_debug/embed (Phase 0 acceptance check) --------------------------------

class EmbedRequest(BaseModel):
    text: str


@app.post("/_debug/embed", tags=["ops"])
async def debug_embed(req: EmbedRequest) -> dict:
    """Embed a string via Gradient — proves the LLM abstraction works end-to-end."""
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")
    llm = get_llm()
    vectors = await llm.embed(
        texts=[req.text],
        model=settings.GRADIENT_EMBED_MODEL,
    )
    v = vectors[0]
    return {
        "dim": len(v),
        "preview": [round(x, 4) for x in v[:6]],
        "model": settings.GRADIENT_EMBED_MODEL,
    }


# ---- Route registration (Phase 1+) -----------------------------------------
# Uncomment as each phase is implemented:

from app.api.auth_routes import router as auth_router
from app.api.student_routes import router as student_router
from app.api.instructor_routes import router as instructor_router
from app.api.admin_routes import router as admin_router
from app.api.billing_routes import router as billing_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(student_router, prefix="/api/student", tags=["student"])
app.include_router(instructor_router, prefix="/api/instructor", tags=["instructor"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(billing_router, prefix="/api/billing", tags=["billing"])

# Database-backed originals require the same Firebase authentication as grading.
from fastapi import Depends
from fastapi.responses import Response
from app.api.student_routes import _get_student_profile
from uuid import UUID
from urllib.parse import quote


@app.get("/api/files/{file_id}/{filename}", tags=["files"])
async def download_demo_file(file_id: UUID, filename: str, user=Depends(_get_student_profile)):
    if not settings.DOCUMENT_DEMO:
        raise HTTPException(404, "Not found")
    async with get_conn(str(user["org_id"])) as conn:
        row = await conn.fetchrow(
            "SELECT owner_uid, filename, content FROM demo_files WHERE id=$1", file_id
        )
    if not row or (row["owner_uid"] != user["uid"] and user["role"] not in {"instructor", "admin"}):
        raise HTTPException(404, "Document not found")
    return Response(
        content=row["content"], media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row['filename'], safe='')}",
                 "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


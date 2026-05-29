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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db.postgres import init_pool, close_pool, get_pool
from app.services.llm_provider import build_llm_from_env
from app.config import settings

# ---- App state --------------------------------------------------------------
_redis = None
_llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _llm

    await init_pool()

    # --- HOTFIX: Update DB Constraint to allow empty string role ---
    try:
        pool = get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;")
                await conn.execute("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('student', 'instructor', 'admin', ''));")
    except Exception as e:
        import traceback
        traceback.print_exc()

    _redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    _llm = build_llm_from_env()

    try:
        yield
    finally:
        await close_pool()
        if _redis:
            await _redis.aclose()


app = FastAPI(
    title=settings.APP_NAME,
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://student-ai-feedback-system.vercel.app", "http://localhost:3000", "http://127.0.0.1:3000", "https://student-ai-feedback-system-g71jryjvw-mibrahimm67s-projects.vercel.app"],
    allow_origin_regex=r"https://student-ai-feedback-system.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Dependency helpers (import these in route files) -----------------------

def get_redis():
    assert _redis is not None, "Redis not initialised"
    return _redis


def get_llm():
    assert _llm is not None, "LLM not initialised"
    return _llm


# ---- /health ----------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health() -> dict:
    pg_ok = "fail"
    redis_ok = "fail"
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        pg_ok = "ok"
    except Exception:
        pass
    try:
        r = get_redis()
        await r.ping()
        redis_ok = "ok"
    except Exception:
        pass

    overall = "ok" if pg_ok == "ok" and redis_ok == "ok" else "degraded"
    return {"status": overall, "postgres": pg_ok, "redis": redis_ok}


# ---- /_debug/embed (Phase 0 acceptance check) --------------------------------

class EmbedRequest(BaseModel):
    text: str


@app.post("/_debug/embed", tags=["ops"])
async def debug_embed(req: EmbedRequest) -> dict:
    """Embed a string via Gradient — proves the LLM abstraction works end-to-end."""
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

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(student_router, prefix="/api/student", tags=["student"])
app.include_router(instructor_router, prefix="/api/instructor", tags=["instructor"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

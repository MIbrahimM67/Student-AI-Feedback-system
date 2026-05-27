"""
Phase 0 minimal API.

Provides:
  - GET  /health           : DB + Redis ping, used as the bring-up check.
  - POST /_debug/embed     : embeds a string via Gradient, returns dim + preview.
                             Lets you prove the LLM provider abstraction works
                             end-to-end before any real route is built.

Everything else (auth, subjects, grading) is added in later phases.
"""
from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.services.llm_provider import build_llm_from_env, ChatMessage  # noqa: F401


# ---- App state holders ------------------------------------------------------

_pg_pool: asyncpg.Pool | None = None
_redis: aioredis.Redis | None = None
_llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pg_pool, _redis, _llm

    # asyncpg uses 'postgresql://' URLs, not 'postgresql+asyncpg://'.
    raw_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    _pg_pool = await asyncpg.create_pool(raw_url, min_size=1, max_size=10)

    _redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    _llm = build_llm_from_env()
    try:
        yield
    finally:
        if _pg_pool:
            await _pg_pool.close()
        if _redis:
            await _redis.aclose()


app = FastAPI(title="AI Feedback System (Phase 0)", lifespan=lifespan)


# ---- /health ----------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    pg_ok, redis_ok = "fail", "fail"
    try:
        assert _pg_pool is not None
        async with _pg_pool.acquire() as conn:
            await conn.execute("SELECT 1")
        pg_ok = "ok"
    except Exception:  # noqa: BLE001
        pass
    try:
        assert _redis is not None
        await _redis.ping()
        redis_ok = "ok"
    except Exception:  # noqa: BLE001
        pass
    overall = "ok" if pg_ok == "ok" and redis_ok == "ok" else "degraded"
    return {"status": overall, "postgres": pg_ok, "redis": redis_ok}


# ---- /_debug/embed ----------------------------------------------------------

class EmbedRequest(BaseModel):
    text: str


@app.post("/_debug/embed")
async def debug_embed(req: EmbedRequest) -> dict:
    """Embed a single string. Returns the dimension and a 6-value preview."""
    if not _llm:
        raise HTTPException(503, "LLM provider not initialised")
    model = os.environ.get("GRADIENT_EMBED_MODEL", "bge-m3")
    vectors = await _llm.embed(texts=[req.text], model=model)
    v = vectors[0]
    return {"dim": len(v), "preview": [round(x, 4) for x in v[:6]], "model": model}

"""
GradeWise v3 — Postgres async connection pool.

The API MUST connect as app_user (not the Postgres superuser) so that
Row-Level Security policies are enforced on every query.

Usage in a route:
    async with get_conn() as conn:
        await conn.execute("SET LOCAL app.current_org_id = $1", org_id)
        row = await conn.fetchrow("SELECT * FROM subjects WHERE id = $1", subject_id)
"""
from __future__ import annotations

import os
import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    raw_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    _pool = await asyncpg.create_pool(raw_url, min_size=2, max_size=20)


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn(org_id: str | None = None) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Yields a connection with RLS org context set when org_id is provided.
    Always use this — never acquire from the pool directly in route handlers.
    """
    assert _pool is not None, "Database pool not initialised. Call init_pool() at startup."
    async with _pool.acquire() as conn:
        if org_id:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.current_org_id', $1, true)", org_id)
                yield conn
        else:
            yield conn


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "Database pool not initialised."
    return _pool

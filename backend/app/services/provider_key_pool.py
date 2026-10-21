"""Share round-robin selection and cooldowns without storing API keys in Postgres."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import re
import time

import httpx


class KeysCoolingDown(RuntimeError):
    pass


class PostgresCooldownStore:
    async def load(self, fingerprints):
        from app.db.postgres import get_conn
        async with get_conn() as conn:
            rows = await conn.fetch(
                "SELECT key_hash, EXTRACT(EPOCH FROM blocked_until) AS until "
                "FROM provider_key_cooldowns WHERE key_hash = ANY($1::text[]) "
                "AND blocked_until > now()", list(fingerprints),
            )
        return {r["key_hash"]: float(r["until"]) for r in rows}

    async def save(self, fingerprint, until):
        from app.db.postgres import get_conn
        async with get_conn() as conn:
            await conn.execute(
                "INSERT INTO provider_key_cooldowns (key_hash, blocked_until) VALUES ($1, $2) "
                "ON CONFLICT (key_hash) DO UPDATE SET blocked_until = "
                "GREATEST(provider_key_cooldowns.blocked_until, EXCLUDED.blocked_until)",
                fingerprint, datetime.fromtimestamp(until, timezone.utc),
            )


def cooldown_seconds(response: httpx.Response) -> float:
    """Groq request-count headers are daily; token-count headers are per minute."""
    text = response.text.lower()
    daily = re.search(r"\b(tpd|rpd|daily)\b|(?:tokens|requests) per day|day limit", text)
    if daily or response.headers.get("x-ratelimit-remaining-requests") == "0":
        return 86400.0
    if response.status_code in {401, 403}:
        return 86400.0
    retry = response.headers.get("retry-after", "")
    try:
        return max(1.0, float(retry))
    except ValueError:
        if retry:
            from email.utils import parsedate_to_datetime
            try:
                return max(1.0, parsedate_to_datetime(retry).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
    reset = response.headers.get("x-ratelimit-reset-tokens", "")
    parts = re.findall(r"([\d.]+)(ms|s|m|h)", reset)
    if parts:
        return max(1.0, sum(float(n) * {"ms": .001, "s": 1, "m": 60, "h": 3600}[u] for n, u in parts))
    return 60.0 if response.status_code == 429 else 5.0


class KeyPool:
    def __init__(self, keys, *, store=None, clock=time.time):
        self.fingerprints = [hashlib.sha256(key.encode()).hexdigest() for key in keys]
        self.blocked = {}
        self.cursor = 0
        self.lock = asyncio.Lock()
        self.store = store
        self.clock = clock

    async def select(self, attempted):
        async with self.lock:
            if self.store:
                # Fail closed if durable state is unavailable: never silently retry
                # an exhausted credential after a process restart.
                persisted = await self.store.load(self.fingerprints)
                for key, until in persisted.items():
                    self.blocked[key] = max(self.blocked.get(key, 0), until)
            now = self.clock()
            for offset in range(len(self.fingerprints)):
                index = (self.cursor + offset) % len(self.fingerprints)
                if index not in attempted and self.blocked.get(self.fingerprints[index], 0) <= now:
                    self.cursor = (index + 1) % len(self.fingerprints)
                    return index
        return None

    async def block(self, index, seconds):
        fingerprint = self.fingerprints[index]
        async with self.lock:
            until = max(self.blocked.get(fingerprint, 0), self.clock() + seconds)
            self.blocked[fingerprint] = until
            if self.store:
                await self.store.save(fingerprint, until)


_pools = {}


def shared_key_pool(keys, *, persistent=False):
    identity = (tuple(hashlib.sha256(k.encode()).hexdigest() for k in keys), persistent)
    if identity not in _pools:
        _pools[identity] = KeyPool(keys, store=PostgresCooldownStore() if persistent else None)
    return _pools[identity]

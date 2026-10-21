"""Credential rotation uses synthetic keys and an HTTP mock, never real AI calls."""
import asyncio

import httpx
import pytest

from app.services import provider_key_pool as pools
from app.services.llm_provider import ChatMessage, ResilientLLM, RotatingProvider, build_dedicated_llm_from_env
from app.config import settings


@pytest.fixture(autouse=True)
def clear_pools(monkeypatch):
    pools._pools.clear()
    # The test transport is entirely local; ignore the execution host's proxy.
    for key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(key, raising=False)


class MemoryStore:
    def __init__(self):
        self.rows = {}

    async def load(self, fingerprints):
        return {k: v for k, v in self.rows.items() if k in fingerprints}

    async def save(self, fingerprint, until):
        self.rows[fingerprint] = until


def provider(handler, *, count=4):
    p = RotatingProvider([f"synthetic-{i}" for i in range(count)], "https://inference.test/v1")
    for client in p.providers:
        client._client = httpx.AsyncClient(
            base_url="https://inference.test/v1",
            headers=client._client.headers,
            transport=httpx.MockTransport(handler),
        )
    return p


def ok():
    return httpx.Response(200, json={"choices": [{"message": {"content": "graded"}}]})


async def chat(p):
    return await p.chat(messages=[ChatMessage("user", "answer")], model="unchanged-model")


@pytest.mark.asyncio
async def test_four_keys_rotate_between_requests_without_changing_model():
    seen = []
    def handle(req):
        import json
        seen.append((req.headers["Authorization"], json.loads(req.content)["model"]))
        return ok()
    p = provider(handle)
    for _ in range(8):
        await chat(p)
    assert seen == [(f"Bearer synthetic-{i % 4}", "unchanged-model") for i in range(8)]


@pytest.mark.asyncio
async def test_daily_limit_fails_over_and_is_not_retried_until_24_hours():
    seen, now = [], [1000.0]
    def handle(req):
        key = req.headers["Authorization"]
        seen.append(key)
        if key == "Bearer synthetic-0":
            return httpx.Response(429, json={"error": {"message": "Tokens per day (TPD) limit reached"}})
        return ok()
    p = provider(handle, count=2)
    p.pool.clock = lambda: now[0]
    await chat(p)
    now[0] += 86399
    await chat(p)
    assert seen == ["Bearer synthetic-0", "Bearer synthetic-1", "Bearer synthetic-1"]
    now[0] += 1
    await chat(p)
    assert seen[-2:] == ["Bearer synthetic-0", "Bearer synthetic-1"]


@pytest.mark.asyncio
async def test_minute_limit_uses_retry_after_and_immediate_alternative():
    seen, now = [], [1000.0]
    def handle(req):
        seen.append(req.headers["Authorization"])
        if len(seen) == 1:
            return httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "tokens per minute"}})
        return ok()
    p = provider(handle, count=2)
    p.pool.clock = lambda: now[0]
    await chat(p)
    await chat(p)
    assert seen == ["Bearer synthetic-0", "Bearer synthetic-1", "Bearer synthetic-1"]
    now[0] += 7
    await chat(p)
    assert seen[-1] == "Bearer synthetic-0"


@pytest.mark.asyncio
async def test_daily_cooldown_survives_new_process_state():
    store = MemoryStore()
    first = pools.KeyPool(["synthetic"], store=store, clock=lambda: 1000)
    await first.block(0, 86400)
    fresh = pools.KeyPool(["synthetic"], store=store, clock=lambda: 2000)
    assert await fresh.select(set()) is None
    fresh.clock = lambda: 87400
    assert await fresh.select(set()) == 0
    assert "synthetic" not in str(store.rows)


@pytest.mark.asyncio
async def test_shared_pool_survives_factory_recreation():
    first = provider(lambda _: ok())
    await first.pool.block(0, 86400)
    second = provider(lambda _: ok())
    assert first.pool is second.pool
    assert await second.pool.select(set()) == 1


@pytest.mark.asyncio
async def test_no_calls_when_every_key_is_cooling_down():
    p = provider(lambda _: pytest.fail("A cooling-down key was contacted"))
    for i in range(4):
        await p.pool.block(i, 86400)
    with pytest.raises(pools.KeysCoolingDown):
        await chat(p)


@pytest.mark.asyncio
async def test_all_daily_drained_keys_fail_without_outer_retry_sleep(monkeypatch):
    seen = []
    def handle(req):
        seen.append(req.headers["Authorization"])
        return httpx.Response(429, headers={"retry-after": "86400"}, json={"error": {"message": "TPD reached"}})
    async def no_sleep(_):
        pytest.fail("Daily exhaustion must not sleep in the retry wrapper")
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    llm = ResilientLLM(provider(handle))
    with pytest.raises(pools.KeysCoolingDown):
        await chat(llm)
    with pytest.raises(pools.KeysCoolingDown):
        await chat(llm)
    assert seen == [f"Bearer synthetic-{i}" for i in range(4)]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 500, 502, 503, 504])
async def test_credential_and_transient_failures_try_next_key(status):
    seen = []
    def handle(req):
        seen.append(req.headers["Authorization"])
        return httpx.Response(status, json={"error": {"message": "unavailable"}}) if len(seen) == 1 else ok()
    p = provider(handle)
    await chat(p)
    assert seen == ["Bearer synthetic-0", "Bearer synthetic-1"]


@pytest.mark.asyncio
async def test_bad_payload_does_not_consume_all_credentials():
    seen = []
    def handle(req):
        seen.append(req.headers["Authorization"])
        return httpx.Response(400, json={"error": {"message": "invalid model"}})
    with pytest.raises(httpx.HTTPStatusError):
        await chat(provider(handle))
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_concurrent_selections_are_balanced():
    p = pools.KeyPool([str(i) for i in range(4)])
    assert await asyncio.gather(*(p.select(set()) for _ in range(12))) == [0, 1, 2, 3] * 3


@pytest.mark.asyncio
async def test_persistence_failure_never_retries_an_unknown_cooldown():
    class BrokenStore:
        async def load(self, _):
            raise RuntimeError("database unavailable")
    p = pools.KeyPool(["synthetic"], store=BrokenStore())
    with pytest.raises(RuntimeError, match="database unavailable"):
        await p.select(set())


def test_daily_headers_and_duration_units():
    assert pools.cooldown_seconds(httpx.Response(429, headers={"x-ratelimit-remaining-requests": "0", "retry-after": "2"})) == 86400
    assert pools.cooldown_seconds(httpx.Response(429, headers={"x-ratelimit-reset-tokens": "1m7.5s"})) == 67.5
    assert pools.cooldown_seconds(httpx.Response(429, headers={"x-ratelimit-reset-tokens": "1500ms"})) == 1.5


def test_factory_deduplicates_single_and_multiple_key_configuration(monkeypatch):
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_BASE_URL", "https://inference.test/v1")
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_TOKEN", "synthetic-0")
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_TOKENS", " synthetic-0,synthetic-1,,synthetic-2 ")
    monkeypatch.setattr(settings, "DOCUMENT_DEMO", False)
    llm = build_dedicated_llm_from_env()
    assert len(llm.primary.providers) == 3
    assert llm.primary.name == "dedicated"


def test_multiple_keys_enable_high_context_document_routing(monkeypatch):
    from app.router.router import _dedicated_available
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_BASE_URL", "https://inference.test/v1")
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_TOKEN", "")
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_TOKENS", "synthetic-0,synthetic-1")
    assert _dedicated_available()
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_TOKENS", " , ")
    assert not _dedicated_available()

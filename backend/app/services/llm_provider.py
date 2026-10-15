"""
GradeWise v3 — provider-agnostic LLM service.

Single chokepoint for every chat / embed / rerank call in the app.
Switching providers (DigitalOcean Gradient → Anthropic → OpenAI) is a
config change, not a code change.

Never call a raw provider directly from pipeline code — always go through
ResilientLLM.
"""
from __future__ import annotations

import os
import asyncio
import hashlib
import time
import logging
import re
from datetime import datetime, timedelta, timezone
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence

import httpx

logger = logging.getLogger(__name__)


def _strip_thinking(text: str) -> str:
    """Remove Qwen-style hidden reasoning blocks from provider output."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if cleaned:
        return cleaned
    if "<think>" in text.lower():
        return re.sub(r"(?is)^.*?<think>.*", "", text).strip()
    return text.strip()


# ---- Data types -------------------------------------------------------------

@dataclass
class ChatMessage:
    role: str   # "system" | "user" | "assistant"
    content: str | list[dict[str, Any]]


@dataclass
class ChatResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


# ---- Provider interface -----------------------------------------------------

class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_format: str | None = None,  # "json_object" forces strict JSON
    ) -> ChatResponse: ...

    @abstractmethod
    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]: ...

    @abstractmethod
    async def rerank(
        self, query: str, documents: Sequence[str], *, model: str, top_k: int = 6
    ) -> list[tuple[int, float]]:
        """Returns [(original_index, score)] sorted by score desc."""
        ...


# ---- DigitalOcean Gradient implementation -----------------------------------
from app.services.rate_limiter import acquire_slot, update_from_headers
import random

class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 90.0,
        *,
        name: str = "openai-compatible",
        rate_limited: bool = False,
    ):
        self.name = name
        self._rate_limited = rate_limited
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_format: str | None = None,
    ) -> ChatResponse:
        body: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json_object":
            body["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        if self._rate_limited:
            await asyncio.to_thread(acquire_slot)
        r = await self._client.post("/chat/completions", json=body)
        if self._rate_limited:
            await asyncio.to_thread(update_from_headers, r.headers)
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage", {})
        return ChatResponse(
            text=_strip_thinking(data["choices"][0]["message"]["content"]),
            model=model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]:
        if self._rate_limited:
            await asyncio.to_thread(acquire_slot)
        r = await self._client.post(
            "/embeddings",
            json={"model": model, "input": list(texts)},
        )
        if self._rate_limited:
            await asyncio.to_thread(update_from_headers, r.headers)
        r.raise_for_status()
        data = r.json()
        return [item["embedding"] for item in data["data"]]

    async def rerank(
        self, query: str, documents: Sequence[str], *, model: str, top_k: int = 6
    ) -> list[tuple[int, float]]:
        if self._rate_limited:
            await asyncio.to_thread(acquire_slot)
        r = await self._client.post(
            "/rerank",
            json={
                "model": model,
                "query": query,
                "documents": list(documents),
                "top_n": top_k,
            },
        )
        if self._rate_limited:
            await asyncio.to_thread(update_from_headers, r.headers)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        return [(item["index"], item["relevance_score"]) for item in results]



class GroqKeysUnavailable(RuntimeError):
    """All configured Groq credentials are cooling down or unavailable."""


class RotatingGroqProvider(LLMProvider):
    """Share a process-wide key pool across grading stages without logging secrets."""

    name = "dedicated"

    def __init__(self, tokens: Sequence[str], base_url: str, timeout: float = 120.0):
        self._providers = [
            OpenAICompatibleProvider(token, base_url, timeout, name=f"dedicated-slot-{i + 1}")
            for i, token in enumerate(dict.fromkeys(token for token in tokens if token))
        ]
        if not self._providers:
            raise ValueError("At least one dedicated inference token is required")
        self._cooldown_until = [0.0] * len(self._providers)
        self._org_by_slot: dict[int, str] = {}
        self._cursor = 0
        self._lock = asyncio.Lock()
        self._load_lock = asyncio.Lock()
        self._loaded = False
        self._fingerprints = [hashlib.sha256(token.encode()).hexdigest() for token in dict.fromkeys(token for token in tokens if token)]

    async def _load_cooldowns(self) -> None:
        if self._loaded:
            return
        async with self._load_lock:
            if self._loaded:
                return
            from app.db.postgres import get_conn
            async with get_conn() as conn:
                rows = await conn.fetch(
                    "SELECT key_fingerprint, organization_id, cooldown_until "
                    "FROM public.groq_key_cooldowns "
                    "WHERE key_fingerprint = ANY($1::text[]) AND cooldown_until > now()",
                    self._fingerprints,
                )
            by_fingerprint = {row['key_fingerprint']: row for row in rows}
            now = datetime.now(timezone.utc)
            async with self._lock:
                for index, fingerprint in enumerate(self._fingerprints):
                    row = by_fingerprint.get(fingerprint)
                    if row:
                        seconds = max(0.0, (row['cooldown_until'] - now).total_seconds())
                        self._cooldown_until[index] = max(self._cooldown_until[index], time.monotonic() + seconds)
                        if row['organization_id']:
                            self._org_by_slot[index] = row['organization_id']
            self._loaded = True

    async def _next_slot(self, attempted: set[int]) -> tuple[int | None, float]:
        async with self._lock:
            now = time.monotonic()
            for offset in range(len(self._providers)):
                index = (self._cursor + offset) % len(self._providers)
                if index not in attempted and self._cooldown_until[index] <= now:
                    self._cursor = (index + 1) % len(self._providers)
                    return index, 0.0
            waits = [until - now for until in self._cooldown_until if until > now]
            return None, min(waits) if waits else 0.0

    async def _cool_down(self, index: int, seconds: float, *, org_id: str | None = None, daily: bool = False) -> None:
        async with self._lock:
            if org_id:
                self._org_by_slot[index] = org_id
            until = time.monotonic() + seconds
            affected = [
                i for i in range(len(self._providers))
                if i == index or (daily and org_id and self._org_by_slot.get(i) == org_id)
            ]
            for i in affected:
                self._cooldown_until[i] = max(self._cooldown_until[i], until)
        from app.db.postgres import get_conn
        until_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        try:
            async with get_conn() as conn:
                for i in affected:
                    await conn.execute(
                        "INSERT INTO public.groq_key_cooldowns "
                        "(key_fingerprint, organization_id, cooldown_until, reason) VALUES ($1,$2,$3,$4) "
                        "ON CONFLICT (key_fingerprint) DO UPDATE SET "
                        "organization_id=COALESCE(EXCLUDED.organization_id, groq_key_cooldowns.organization_id), "
                        "cooldown_until=GREATEST(groq_key_cooldowns.cooldown_until, EXCLUDED.cooldown_until), "
                        "reason=EXCLUDED.reason, updated_at=now()",
                        self._fingerprints[i], self._org_by_slot.get(i), until_at,
                        'daily' if daily else 'temporary',
                    )
        except Exception:
            logger.exception("Could not persist Groq key cooldown; current process will still honor it")
        logger.warning("Groq slot %d cooling down for %.0fs (%s limit)", index + 1, seconds, "daily" if daily else "temporary")

    async def _call(self, operation):
        # A short minute-level cooldown can be retried once. A daily limit is
        # never rechecked in this process for 24 hours.
        last_error: Exception | None = None
        await self._load_cooldowns()
        for cycle in range(2):
            attempted: set[int] = set()
            while len(attempted) < len(self._providers):
                index, wait = await self._next_slot(attempted)
                if index is None:
                    break
                attempted.add(index)
                try:
                    return await operation(self._providers[index])
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    if status == 429:
                        body = exc.response.text
                        daily = any(mark in body.lower() for mark in ("per day", "(tpd)", "(rpd)", "daily limit"))
                        org = re.search(r"organization [`']([^`']+)[`']", body)
                        try:
                            retry_after = float(exc.response.headers.get("retry-after", "30"))
                        except ValueError:
                            retry_after = 30.0
                        await self._cool_down(index, 86400.0 if daily else max(1.0, retry_after), org_id=org.group(1) if org else None, daily=daily)
                        continue
                    if status in (401, 403):
                        await self._cool_down(index, 86400.0)
                        continue
                    if status in (500, 502, 503, 504):
                        await self._cool_down(index, 10.0)
                        continue
                    raise
                except httpx.RequestError as exc:
                    last_error = exc
                    await self._cool_down(index, 10.0)
            _, wait = await self._next_slot(set())
            if cycle == 0 and 0 < wait <= 60:
                await asyncio.sleep(wait + 0.1)
                continue
            break
        raise GroqKeysUnavailable("All configured Groq keys are unavailable; check their organization quotas and retry after cooldown.") from last_error

    async def chat(self, messages: Sequence[ChatMessage], *, model: str, temperature: float = 0.2, max_tokens: int = 2048, response_format: str | None = None) -> ChatResponse:
        return await self._call(lambda provider: provider.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, response_format=response_format))

    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]:
        return await self._call(lambda provider: provider.embed(texts, model=model))

    async def rerank(self, query: str, documents: Sequence[str], *, model: str, top_k: int = 6) -> list[tuple[int, float]]:
        return await self._call(lambda provider: provider.rerank(query, documents, model=model, top_k=top_k))


_DEDICATED_POOLS: dict[tuple[str, ...], RotatingGroqProvider] = {}


def _dedicated_pool(tokens: Sequence[str], base_url: str) -> RotatingGroqProvider:
    key = (base_url, *dict.fromkeys(token for token in tokens if token))
    if key not in _DEDICATED_POOLS:
        _DEDICATED_POOLS[key] = RotatingGroqProvider(key[1:], base_url)
    return _DEDICATED_POOLS[key]


class GradientProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str, timeout: float = 90.0):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            name="gradient",
            rate_limited=True,
        )


# ---- Resilient wrapper: retries + failover ----------------------------------

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ResilientLLM:
    """
    Wraps one or more providers with timeouts, exponential-backoff retries,
    and automatic failover to backup providers.
    """

    def __init__(
        self,
        primary: LLMProvider,
        failover: Sequence[LLMProvider] = (),
        model_overrides: dict[str, str] | None = None,
        max_retries: int = 2,
        base_backoff_s: float = 0.5,
    ):
        self.primary = primary
        self.failover = list(failover)
        self.model_overrides = model_overrides or {}
        self.max_retries = max_retries
        self.base_backoff_s = base_backoff_s

    async def _with_retries(self, op_name: str, fn):
        last_exc: Exception | None = None
        for provider in [self.primary, *self.failover]:
            for attempt in range(self.max_retries + 1):
                try:
                    return await fn(provider)
                except httpx.TimeoutException as e:
                    last_exc = e
                    retryable = True
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    retryable = e.response.status_code in _RETRYABLE_STATUS
                    
                    # Fast-fail hard DO Inference 429s (usually token limits)
                    if e.response.status_code == 429:
                        try:
                            err_data = e.response.json()
                            if err_data.get("error", {}).get("type") == "rate_limit_exceeded_error":
                                retryable = False
                        except Exception:
                            pass
                            
                    if not retryable:
                        logger.error(
                            "LLM %s non-retryable: provider=%s status=%s body=%s",
                            op_name, provider.name,
                            e.response.status_code, e.response.text[:300],
                        )
                        break
                except Exception as e:  # noqa: BLE001
                    last_exc = e
                    logger.exception("LLM %s unexpected error: provider=%s", op_name, provider.name)
                    break

                if attempt < self.max_retries:
                    if isinstance(last_exc, httpx.HTTPStatusError) and last_exc.response.status_code == 429:
                        # PROFESSOR REQUESTED DIAGNOSTIC LOGGING
                        logger.error(
                            "=== 429 DIAGNOSTICS (Attempt %d) ===\n"
                            "Status Code: %s\n"
                            "Headers: %s\n"
                            "Body: %s\n"
                            "=====================================",
                            attempt + 1,
                            last_exc.response.status_code,
                            dict(last_exc.response.headers),
                            last_exc.response.text
                        )
                        
                        if "retry-after" in last_exc.response.headers:
                            base = float(last_exc.response.headers["retry-after"])
                        else:
                            base = min(self.base_backoff_s * (2 ** attempt), 64)
                    else:
                        base = min(self.base_backoff_s * (2 ** attempt), 64)
                        
                    backoff = base + random.uniform(0, 0.5)
                    logger.warning(
                        "LLM %s retry: provider=%s attempt=%d backoff=%.2fs err=%s",
                        op_name, provider.name, attempt + 1, backoff, last_exc,
                    )
                    await asyncio.sleep(backoff)
            logger.error("LLM %s exhausted retries on provider=%s; trying next", op_name, provider.name)
        assert last_exc is not None
        raise last_exc

    async def chat(self, **kwargs) -> ChatResponse:
        async def call(provider: LLMProvider) -> ChatResponse:
            call_kwargs = dict(kwargs)
            if provider.name in self.model_overrides:
                call_kwargs["model"] = self.model_overrides[provider.name]
            return await provider.chat(**call_kwargs)

        return await self._with_retries("chat", call)

    async def embed(self, **kwargs) -> list[list[float]]:
        return await self._with_retries("embed", lambda p: p.embed(**kwargs))

    async def rerank(self, **kwargs) -> list[tuple[int, float]]:
        return await self._with_retries("rerank", lambda p: p.rerank(**kwargs))



# ---- Factory ----------------------------------------------------------------

def build_dedicated_llm_from_env() -> ResilientLLM | None:
    """Build a dedicated (high-capacity) LLM if env vars are configured.
    Returns None if no dedicated endpoint is configured.
    """
    from app.config import settings
    if not settings.DEDICATED_INFERENCE_BASE_URL or not settings.DEDICATED_INFERENCE_TOKEN:
        return None
    backup_tokens = re.split(r"[,;\s]+", os.getenv("DEDICATED_INFERENCE_BACKUP_TOKENS", "").strip())
    dedicated = _dedicated_pool(
        [settings.DEDICATED_INFERENCE_TOKEN, *backup_tokens],
        settings.DEDICATED_INFERENCE_BASE_URL,
    )
    failover: list[LLMProvider] = []
    model_overrides: dict[str, str] = {}

    if (
        settings.DEDICATED_FALLBACK_BASE_URL
        and settings.DEDICATED_FALLBACK_TOKEN
        and settings.DEDICATED_FALLBACK_MODEL
    ):
        failover.append(OpenAICompatibleProvider(
            api_key=settings.DEDICATED_FALLBACK_TOKEN,
            base_url=settings.DEDICATED_FALLBACK_BASE_URL,
            timeout=120.0,
            name="dedicated-fallback",
        ))
        model_overrides["dedicated-fallback"] = settings.DEDICATED_FALLBACK_MODEL

    if settings.GRADIENT_API_KEY:
        failover.append(GradientProvider(
            api_key=settings.GRADIENT_API_KEY,
            base_url=settings.GRADIENT_BASE_URL,
        ))
        model_overrides["gradient"] = settings.GRADIENT_MODEL_SPECIALIST

    return ResilientLLM(
        primary=dedicated,
        failover=failover,
        model_overrides=model_overrides,
        max_retries=1,
        base_backoff_s=2.0,
    )


def build_llm_from_env() -> ResilientLLM:
    """Use the configured dedicated chat model throughout the document demo."""
    from app.config import settings

    if settings.DOCUMENT_DEMO:
        dedicated = build_dedicated_llm_from_env()
        if dedicated:
            # Rubric decomposition and small submissions also enter this factory.
            # Their legacy Gradient model IDs must not reach the dedicated API.
            dedicated.model_overrides[dedicated.primary.name] = settings.DEDICATED_MODEL
            return dedicated

    primary = GradientProvider(
        api_key=settings.GRADIENT_API_KEY,
        base_url=settings.GRADIENT_BASE_URL,
    )
    failover: list[LLMProvider] = []
    return ResilientLLM(primary=primary, failover=failover, max_retries=6, base_backoff_s=2.0)


def build_vision_llm_from_env() -> ResilientLLM | None:
    """Build the vision-capable provider for diagrams, flowcharts, and design images."""
    from app.config import settings

    failover: list[LLMProvider] = []
    model_overrides: dict[str, str] = {}

    if settings.GRADIENT_VISION_OCR_MODEL and settings.GRADIENT_API_KEY:
        failover.append(GradientProvider(
            api_key=settings.GRADIENT_API_KEY,
            base_url=settings.GRADIENT_BASE_URL,
            timeout=180.0,
        ))
        model_overrides["gradient"] = settings.GRADIENT_VISION_OCR_MODEL

    if settings.DEDICATED_VISION_MODEL:
        base_url = settings.DEDICATED_VISION_BASE_URL or settings.DEDICATED_INFERENCE_BASE_URL
        token = settings.DEDICATED_VISION_TOKEN or settings.DEDICATED_INFERENCE_TOKEN
        if base_url and token:
            provider = OpenAICompatibleProvider(
                api_key=token,
                base_url=base_url,
                timeout=180.0,
                name="dedicated-vision",
            )
            return ResilientLLM(
                primary=provider,
                failover=failover,
                model_overrides=model_overrides,
                max_retries=1,
                base_backoff_s=2.0,
            )

    if failover:
        return ResilientLLM(
            primary=failover[0],
            failover=failover[1:],
            model_overrides=model_overrides,
            max_retries=2,
            base_backoff_s=1.0,
        )

    return None



def build_embedding_llm_from_env() -> ResilientLLM | None:
    """Embedding APIs are independent from the Groq/chat-model factory."""
    from app.config import settings
    if not settings.GRADIENT_API_KEY:
        return None
    return ResilientLLM(primary=GradientProvider(api_key=settings.GRADIENT_API_KEY,base_url=settings.GRADIENT_BASE_URL),max_retries=2)


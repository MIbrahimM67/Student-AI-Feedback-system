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
import time
import logging
import re
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
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "GradeWise/3.0"},
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


class GradientProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str, timeout: float = 90.0):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            name="gradient",
            rate_limited=True,
        )


class RotatingProvider(LLMProvider):
    """Try each available credential once, retaining the selected grading model."""
    def __init__(self, keys, base_url, *, persistent=False):
        from app.services.provider_key_pool import shared_key_pool
        self.name = "dedicated"
        self.pool = shared_key_pool(keys, persistent=persistent)
        self.providers = [OpenAICompatibleProvider(
            api_key=key, base_url=base_url, timeout=120.0, name=self.name,
        ) for key in keys]

    async def _call(self, method, *args, **kwargs):
        from app.services.provider_key_pool import KeysCoolingDown, cooldown_seconds
        attempted = set()
        last_error = None
        while len(attempted) < len(self.providers):
            index = await self.pool.select(attempted)
            if index is None:
                break
            attempted.add(index)
            try:
                return await getattr(self.providers[index], method)(*args, **kwargs)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in {401, 403, 429, 500, 502, 503, 504}:
                    raise  # Invalid payload/model is not a credential failure.
                await self.pool.block(index, cooldown_seconds(exc.response))
                last_error = exc
            except httpx.TransportError as exc:
                await self.pool.block(index, 5.0)
                last_error = exc
        # Do not let the outer retry wrapper sleep for a provider's daily
        # Retry-After once every credential has already been tried or skipped.
        raise KeysCoolingDown("All inference credentials are cooling down; retry later.") from last_error

    async def chat(self, *args, **kwargs):
        return await self._call("chat", *args, **kwargs)

    async def embed(self, *args, **kwargs):
        return await self._call("embed", *args, **kwargs)

    async def rerank(self, *args, **kwargs):
        return await self._call("rerank", *args, **kwargs)


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
    keys = list(dict.fromkeys(k.strip() for k in [
        settings.DEDICATED_INFERENCE_TOKEN or "",
        *settings.DEDICATED_INFERENCE_TOKENS.split(","),
    ] if k.strip()))
    if not settings.DEDICATED_INFERENCE_BASE_URL or not keys:
        return None
    dedicated = RotatingProvider(
        keys=keys,
        base_url=settings.DEDICATED_INFERENCE_BASE_URL,
        persistent=settings.INFERENCE_COOLDOWN_PERSISTENCE,
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

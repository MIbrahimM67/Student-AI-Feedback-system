"""
Provider-agnostic LLM service.

This is the single chokepoint for every chat / embed / rerank call in the app.
Switching providers (DigitalOcean Gradient -> Anthropic -> OpenAI -> Together)
is a config change, not a code change.

Why this matters for production:
  * Failover when the primary provider is down or rate-limits.
  * Cost / quality A/B without touching pipeline code.
  * The eval harness can pin a (provider, model) for reproducibility.

Use ResilientLLM everywhere; never call a raw provider directly from the
pipeline.
"""
from __future__ import annotations

import os
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)


# ---- Data types -------------------------------------------------------------

@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


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
        response_format: str | None = None,    # "json_object" forces strict JSON
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
# Endpoint shapes follow OpenAI-style conventions (chat.completions, embeddings).
# If Gradient's actual endpoint paths or response shapes differ, adjust ONLY
# this class — nothing else in the app should care.

class GradientProvider(LLMProvider):
    name = "gradient"

    def __init__(self, api_key: str, base_url: str, timeout: float = 60.0):
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
        r = await self._client.post("/chat/completions", json=body)
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage", {})
        return ChatResponse(
            text=data["choices"][0]["message"]["content"],
            model=model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]:
        r = await self._client.post(
            "/embeddings",
            json={"model": model, "input": list(texts)},
        )
        r.raise_for_status()
        data = r.json()
        return [item["embedding"] for item in data["data"]]

    async def rerank(
        self, query: str, documents: Sequence[str], *, model: str, top_k: int = 6
    ) -> list[tuple[int, float]]:
        # NOTE: rerank endpoint shape varies by provider — verify Gradient's
        # actual API and adjust the request/response parsing if needed.
        r = await self._client.post(
            "/rerank",
            json={
                "model": model,
                "query": query,
                "documents": list(documents),
                "top_n": top_k,
            },
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        return [(item["index"], item["relevance_score"]) for item in results]


# ---- Resilient wrapper: retries with backoff + failover ---------------------

# Retryable failure modes:
#   - request timeouts
#   - HTTP 429 (rate-limited), 5xx server errors
# Anything else (auth, validation) is NOT retried — that's a bug, not a blip.

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ResilientLLM:
    """
    Wraps providers with timeouts, retries-with-exponential-backoff, and
    automatic failover to backup providers.

    primary  : the cheap/preferred provider (e.g. Gradient).
    failover : ordered list of backups (e.g. [Anthropic, OpenAI]). Empty for now.
    """

    def __init__(
        self,
        primary: LLMProvider,
        failover: Sequence[LLMProvider] = (),
        max_retries: int = 2,
        base_backoff_s: float = 0.5,
    ):
        self.primary = primary
        self.failover = list(failover)
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
                    if not retryable:
                        logger.error(
                            "LLM %s non-retryable on provider=%s status=%s body=%s",
                            op_name, provider.name, e.response.status_code, e.response.text[:300],
                        )
                        break
                except Exception as e:  # noqa: BLE001
                    last_exc = e
                    logger.exception("LLM %s unexpected error on provider=%s", op_name, provider.name)
                    break

                if attempt < self.max_retries:
                    backoff = self.base_backoff_s * (2 ** attempt)
                    logger.warning(
                        "LLM %s retry: provider=%s attempt=%d backoff=%.2fs err=%s",
                        op_name, provider.name, attempt + 1, backoff, last_exc,
                    )
                    await asyncio.sleep(backoff)
            logger.error("LLM %s exhausted on provider=%s; trying next", op_name, provider.name)
        assert last_exc is not None
        raise last_exc

    async def chat(self, **kwargs) -> ChatResponse:
        return await self._with_retries("chat", lambda p: p.chat(**kwargs))

    async def embed(self, **kwargs) -> list[list[float]]:
        return await self._with_retries("embed", lambda p: p.embed(**kwargs))

    async def rerank(self, **kwargs) -> list[tuple[int, float]]:
        return await self._with_retries("rerank", lambda p: p.rerank(**kwargs))


# ---- Factory ----------------------------------------------------------------

def build_llm_from_env() -> ResilientLLM:
    primary = GradientProvider(
        api_key=os.environ["GRADIENT_API_KEY"],
        base_url=os.environ["GRADIENT_BASE_URL"],
    )
    # Add failover providers here when you have keys configured. Examples:
    #   AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
    #   OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
    failover: list[LLMProvider] = []
    return ResilientLLM(primary=primary, failover=failover)

# Full-Context Grading via DigitalOcean Dedicated Inference — Implementation Spec

**For:** AI coding agent (Antigravity)
**Goal:** Make full-context (Tier 0) grading work for large submissions by adding a **second LLM backend** — a DigitalOcean **Dedicated Inference** GPU endpoint — alongside the existing serverless endpoint. Keep cheap serverless + RAG for everything that fits.

---

## 0. TL;DR

1. The `429` on large submissions is **not** an RPM limit, **not** a TPM limit, and **not** a context-window overflow. It is a **per-request input-size rejection** on DO's shared **serverless** endpoint, returned as a generic `rate_limit_exceeded_error` with all rate buckets still full.
2. Fix: route large submissions that need full context to a **dedicated** gpt-oss-120b endpoint (full 128k context, no shared per-request guardrail). Use RAG where it makes sense; use serverless Tier 0 for small inputs.
3. This is a **dual-backend** change: add a second `ResilientLLM` client pointed at the dedicated endpoint, and have the router/executor choose the backend per submission.
4. **Do not** resize the Droplet. The Droplet runs the workers; it has nothing to do with the inference limit.

---

## 1. Corrected diagnosis (read first — this supersedes earlier conclusions)

Earlier conclusions to **discard**:

- ❌ "The 429 was an RPM limit all along." The captured 429 headers showed `x-ratelimit-remaining-requests: 119/120` and `x-ratelimit-remaining-tokens-per-minute: 500000/500000` — **both buckets full**. Nothing was throttled by rate.
- ❌ "The model enforces an 8K context (LLaMA-3-style)." `openai-gpt-oss-120b` is the correct DO serverless model string, and gpt-oss-120b's real context window is **128k**. 13,201 tokens is nowhere near it. The error type was `rate_limit_exceeded_error`, not a context error.
- ❌ The probe's "silent death at ~4,000 words" is **inconclusive** (likely a script timeout or an out-of-memory kill on the small Droplet), and it contradicts the clean 429 captured at 13,201 tokens. Do not treat 8,192 as a proven cap.

What is actually true:

- The failure is **size-correlated**: sub-300-token requests always succeed; the 13,201-token request always fails, even on a fully idle worker, on the first attempt.
- DO's **serverless** endpoint imposes a per-request input ceiling **well below** the model's 128k context and surfaces over-cap requests as a `429 rate_limit_exceeded_error` (request rejected before it's counted, so buckets don't decrement). The exact ceiling is unknown; the probe needs re-running properly if we ever want to push more through serverless.
- A 429 of this type is **non-retryable** — waiting/jitter/backoff can never make an oversized request succeed.

---

## 2. Solution architecture

Two LLM backends:

- **Serverless** (`inference.do-ai.run`, `openai-gpt-oss-120b`, per-token billing): small submissions (Tier 0) and RAG/Map-Reduce chunks (small inputs).
- **Dedicated** (GPU endpoint, `openai/gpt-oss-120b`, GPU-hour billing): true full-context Tier 0 for large submissions where RAG isn't appropriate.

Routing priority per submission:

1. Fits the conservative serverless budget → **Tier 0 on serverless** (cheapest, most submissions).
2. Larger than serverless budget **and** RAG makes sense (substantial, retrievable reference; localizable rubric criteria) → **Tier 2 RAG** (or **Tier 1 Tree** if reference is structured), run on **serverless** (retrieval shrinks input under the cap).
3. Larger than serverless budget **and** RAG does **not** make sense (little/no reference, or rubric needs holistic reading of the whole document) → **Tier 0 full-context on the dedicated endpoint**.
4. Submission alone exceeds the dedicated context window (~128k) → **Tier 3 Map-Reduce** (chunks run on serverless).

---

## 3. Prerequisite — create the dedicated endpoint (human/console task)

> This step is done by a human in the DigitalOcean console (it involves billing). Antigravity should **not** attempt it. The implementation below reads the endpoint URL and token from env vars that get filled once the endpoint is **Active**.

- DO Console → **Inference → Dedicated Inference → Deploy Dedicated Inference**.
- **Region:** ATL1, NYC2, or TOR1 (only these support dedicated inference). Grading is async, so latency is irrelevant.
- **Model:** Open Source tab → `openai/gpt-oss-120b` (fits on a single 80 GB GPU; a 1-GPU plan is enough).
- Name it → Deploy. Provisions in a few minutes (Provisioning → Active).
- From the deployment page, copy the **Public Endpoint** (`https://<id>-public-dedicated-inference.do-infra.ai/v1/chat/completions`) and the **dedicated access token**.
- **Billing note:** dedicated is charged by **GPU-hour while active**, not per token. For bursty grading, consider scripting create/destroy around batch runs via `POST`/`DELETE /v2/dedicated-inferences`.

These two values populate `DEDICATED_INFERENCE_BASE_URL` and `DEDICATED_INFERENCE_TOKEN` below.

---

## 4. Implementation steps (Antigravity)

1. **Config / env vars.** Add:
   - `DO_TOKEN` (existing serverless token)
   - `SERVERLESS_BASE_URL = https://inference.do-ai.run/v1`
   - `SERVERLESS_MODEL_SLUG = openai-gpt-oss-120b`  ← **hyphen** form
   - `DEDICATED_INFERENCE_BASE_URL` (e.g. `https://<id>-public-dedicated-inference.do-infra.ai/v1`) — filled once endpoint is Active
   - `DEDICATED_INFERENCE_TOKEN`
   - `DEDICATED_MODEL_SLUG = openai/gpt-oss-120b`  ← **slash** form (differs from serverless!)
2. **Second LLM client.** Instantiate a second `ResilientLLM` for the dedicated backend (reuse the existing class; only base_url / api_key / model differ). See §6.
3. **Router.** Replace `route()` to return a `(tier, backend)` decision per §5.
4. **Executor.** Where a tier is executed, select the client by `decision.backend` (serverless vs dedicated). Tier 2/3 chunks and Tier 0 small inputs use serverless; Tier 0 large inputs use dedicated.
5. **Keep** the already-implemented fast-fail on `rate_limit_exceeded_error` and the conservative serverless budget. They remain correct.
6. **Model-slug gotcha.** Dedicated requests must send `openai/gpt-oss-120b` (slash); serverless sends `openai-gpt-oss-120b` (hyphen). Wire each client to its own slug — do not share one model string.

---

## 5. `router.py`

```python
from dataclasses import dataclass

# --- budgets ---
SERVERLESS_INPUT_CAP   = 8192                      # conservative; NOT a proven cap
TIER0_SERVERLESS_BUDGET = int(SERVERLESS_INPUT_CAP * 0.8)   # 6553
DEDICATED_CONTEXT_BUDGET = int(120_000 * 0.9)      # gpt-oss-120b 128k window, headroom for output
RAG_MIN_REFERENCE_TOKENS = 1500                    # tune: min reference size worth retrieving from


@dataclass
class RoutingDecision:
    tier: "Tier"
    backend: str   # "serverless" | "dedicated"


def rag_is_appropriate(sub_payload, ref_payload) -> bool:
    """
    RAG helps only when there is substantial, retrievable reference material AND
    the rubric criteria can be matched to localized passages. Otherwise (little/no
    reference, or holistic rubric) we want true full-context grading instead.
    DEFAULT HEURISTIC — tune to your rubric semantics.
    """
    return ref_payload.has_structure and ref_payload.est_tokens >= RAG_MIN_REFERENCE_TOKENS


def route(sub_payload, ref_payload) -> RoutingDecision:
    combined = sub_payload.est_tokens + ref_payload.est_tokens
    logger.info("Routing payload: combined_tokens=%d, ref_has_structure=%s",
                combined, ref_payload.has_structure)

    # 1. Fits cheap serverless full-context
    if combined <= TIER0_SERVERLESS_BUDGET:
        logger.info("Decision: Tier 0 (Context) on serverless")
        return RoutingDecision(Tier.CONTEXT, "serverless")

    # 2. Submission alone too big even for the dedicated context window -> must split
    if sub_payload.est_tokens > DEDICATED_CONTEXT_BUDGET:
        logger.info("Decision: Tier 3 (Map-Reduce) on serverless")
        return RoutingDecision(Tier.MAP_REDUCE, "serverless")

    # 3. Large, but RAG makes sense -> retrieve, run on serverless
    if rag_is_appropriate(sub_payload, ref_payload):
        if ref_payload.has_structure:
            logger.info("Decision: Tier 1 (Tree) on serverless")
            return RoutingDecision(Tier.TREE, "serverless")
        logger.info("Decision: Tier 2 (Vector/RAG) on serverless")
        return RoutingDecision(Tier.VECTOR, "serverless")

    # 4. Large, RAG not appropriate -> true full-context on the dedicated GPU endpoint
    logger.info("Decision: Tier 0 (Context) on DEDICATED")
    return RoutingDecision(Tier.CONTEXT, "dedicated")
```

---

## 6. Client wiring (sketch — match to the real `ResilientLLM` signature)

```python
import os

serverless_llm = ResilientLLM(
    base_url=os.environ["SERVERLESS_BASE_URL"],          # https://inference.do-ai.run/v1
    api_key=os.environ["DO_TOKEN"],
    model=os.environ["SERVERLESS_MODEL_SLUG"],           # openai-gpt-oss-120b  (hyphen)
)

dedicated_llm = ResilientLLM(
    base_url=os.environ["DEDICATED_INFERENCE_BASE_URL"], # https://<id>-public-dedicated-inference.do-infra.ai/v1
    api_key=os.environ["DEDICATED_INFERENCE_TOKEN"],
    model=os.environ.get("DEDICATED_MODEL_SLUG", "openai/gpt-oss-120b"),  # slash
)

def client_for(decision: "RoutingDecision") -> "ResilientLLM":
    return dedicated_llm if decision.backend == "dedicated" else serverless_llm
```

In the executor:

```python
decision = route(sub_payload, ref_payload)
llm = client_for(decision)
# dispatch on decision.tier as before, passing `llm` to the grading call
```

---

## 7. Acceptance criteria

- The previously failing **13,201-token PDF grades successfully via Tier 0 on the `dedicated` backend**, full context, zero `429`.
- Small submissions still grade on **serverless** Tier 0.
- No single request above `TIER0_SERVERLESS_BUDGET` is ever sent to the serverless endpoint.
- If serverless ever returns `rate_limit_exceeded_error`, the worker **fast-fails** (no 6-retry storm).
- Dedicated requests use model slug `openai/gpt-oss-120b`; serverless uses `openai-gpt-oss-120b`.

---

## 8. Open items / to confirm

- Fill `DEDICATED_INFERENCE_BASE_URL` and `DEDICATED_INFERENCE_TOKEN` once the endpoint is **Active** (grading via the dedicated path won't work until then).
- Confirm the dedicated deployment's context length (assumed 128k); adjust `DEDICATED_CONTEXT_BUDGET` if different.
- Tune `rag_is_appropriate()` and `RAG_MIN_REFERENCE_TOKENS` to the real rubric semantics.
- Cost control: dedicated bills GPU-hours while active — consider scripted create/destroy around batch grading runs.
- Do **not** resize the Droplet for this; the Droplet only runs the workers.
```

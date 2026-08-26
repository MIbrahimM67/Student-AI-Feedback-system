# Grading Pipeline 429 Fix — Implementation Spec

**For:** AI coding agent (Antigravity)
**Goal:** Eliminate `429 Too Many Requests` from the DigitalOcean Inference API **without degrading grading quality**.
**Touch points:** `llm_provider.py` (`ResilientLLM` wrapper), `router.py` (Routing Ladder), Celery worker config.

---

## 0. TL;DR for the implementer

The `429` is a **requests-per-minute (RPM) problem, not a token/payload-size problem.** Do **not** shrink payloads or chunk documents to "fix" it. Instead:

1. Add a **shared, self-tuning request limiter** (Redis-backed, shared across all Celery workers) that paces outgoing calls *before* sending.
2. On `429`, honor the server's **`retry-after`** header and add **jitter** to backoff.
3. Cap **in-flight concurrency** below the worker count.
4. Keep **Tier 0 (full-context grading)** as the default — it is the highest-quality mode and the rate fix makes it safe to use.
5. Restrict **Tier 3 (Map-Reduce)** to true context-window overflows only, not to the 5,000-token rate trigger.

---

## 1. Root-cause diagnosis (read before changing anything)

The original design assumed a large token payload (13,201 tokens) "exhausted the rate limit quota." This is incorrect.

DigitalOcean's inference rate limits are **per OAuth token and counted in requests, not tokens**:

- Default ceiling: **5,000 requests/hour** and a **250 requests/minute** burst limit.
- The limit counts **requests**. A 5,500-token request and a 13,000-token request each count as exactly **one** request.
- On throttle, the API returns a `429` with a **`retry-after`** header (seconds to wait), plus `ratelimit-limit`, `ratelimit-remaining`, and `ratelimit-reset` headers on normal responses.
- Reference: https://docs.digitalocean.com/reference/api/reference/inference-apis/

**Consequences for the existing architecture:**

- **Tier 2 (RAG) does not help the 429.** Reducing 13k → 5.5k tokens leaves the request count unchanged (still 1 request), while risking quality loss by dropping reference passages the rubric needs.
- **Tier 3 (Map-Reduce) makes the 429 worse.** Splitting one 50-page essay into ~12 chunks turns 1 request into ~12 requests against the exact request-count quota that is blocking the pipeline.
- **The real trigger is a burst/concurrency + retry storm:** 4 Celery workers (`ForkPoolWorker-*`) fire simultaneously, plus any embedding calls for RAG share the same token quota. The current backoff schedule (`2, 4, 8, 16, 32, 64s`) has **no jitter**, so all failed workers retry at the same instant and re-collide.

---

## 2. Recommended solution

Move rate control to the rate layer. Keep grading quality intact.

### 2.1 Shared, self-tuning request limiter (PRIMARY FIX)

Because there are 4 Celery workers, the limiter **must be shared** (Redis). An in-process limiter lets each worker assume it owns the whole quota, which reproduces the bug.

The limiter is **self-tuning**: it reads the real ceiling from the API response headers, so the exact RPM number does not need to be known in advance.

```python
# rate_limiter.py
import time, redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

RPM_KEY        = "do_infer:rpm_limit"      # discovered ceiling (from headers)
REMAINING_KEY  = "do_infer:remaining"      # remaining in current window (from headers)
RESET_KEY      = "do_infer:reset_at"       # unix epoch when window resets (from headers)
WINDOW_KEY     = "do_infer:window"         # sliding-window request log

FALLBACK_RPM   = 120     # conservative guess used only before first header arrives
SAFETY_FACTOR  = 0.85    # use 85% of the discovered ceiling for headroom


def acquire_slot():
    """Block until a request slot is free. Call immediately before every LLM request."""
    while True:
        now = time.time()
        limit = int(float(r.get(RPM_KEY) or FALLBACK_RPM) * SAFETY_FACTOR)
        pipe = r.pipeline()
        pipe.zremrangebyscore(WINDOW_KEY, 0, now - 60)   # drop entries older than 60s
        pipe.zcard(WINDOW_KEY)
        _, count = pipe.execute()
        if count < limit:
            r.zadd(WINDOW_KEY, {f"{now}:{count}": now})
            r.expire(WINDOW_KEY, 60)
            return
        oldest = r.zrange(WINDOW_KEY, 0, 0, withscores=True)
        sleep_for = (oldest[0][1] + 60) - now if oldest else 1.0
        time.sleep(max(sleep_for, 0.05))


def update_from_headers(headers):
    """Call after every response (success OR 429) to self-tune the limiter."""
    if "ratelimit-limit" in headers:
        r.set(RPM_KEY, int(headers["ratelimit-limit"]))
    if "ratelimit-remaining" in headers:
        r.set(REMAINING_KEY, int(headers["ratelimit-remaining"]))
    if "ratelimit-reset" in headers:
        r.set(RESET_KEY, float(headers["ratelimit-reset"]))
```

> **Note on the ceiling:** `ratelimit-limit` from DigitalOcean is typically expressed as the **hourly** quota (5,000). If the burst (per-minute) limit is the binding constraint, derive an effective per-minute target from observed `429`s and the `retry-after` values, or set `RPM_KEY` manually once the real per-minute limit is known. Start with `FALLBACK_RPM = 120` and tune upward.

### 2.2 Backoff: honor `retry-after`, add jitter (in `ResilientLLM`)

Replace the fixed `2, 4, 8, 16, 32, 64` schedule. On a `429`, sleep for the server-provided `retry-after`; on other transient errors, use exponential backoff **with jitter** so retries de-synchronize.

```python
# inside ResilientLLM, in the 429 / retry path
import random

MAX_RETRIES = 6

def _sleep_before_retry(resp, attempt):
    if resp is not None and resp.status_code == 429 and "retry-after" in resp.headers:
        base = float(resp.headers["retry-after"])
    else:
        base = min(2 ** attempt, 64)          # exponential, capped
    time.sleep(base + random.uniform(0, 0.5))  # jitter breaks the thundering herd
```

Every call path:
`acquire_slot()` → send request → `update_from_headers(resp.headers)` → on 429, `_sleep_before_retry(resp, attempt)` and retry up to `MAX_RETRIES`.

### 2.3 Cap in-flight concurrency

Decouple "submissions being processed" from "simultaneous LLM calls." Two acceptable approaches:

- **Celery:** route LLM grading tasks through a dedicated queue with worker concurrency set to **2–3** (not 4), or
- **Semaphore:** wrap the LLM call site in a shared semaphore sized to 2–3.

The shared limiter (2.1) is the primary control; this is defense-in-depth against spikes.

### 2.4 Keep quality intact — fix the Routing Ladder (`router.py`)

The rate fix removes the reason to degrade prompts. Update the routing logic:

- **Default to Tier 0 (Context Stuffing)** for the overwhelming majority of submissions. 13k tokens is well within modern context windows; full-context grading is the highest-quality mode.
- **Tier 2 (RAG)** — keep available, but only as a deliberate cost/latency optimization, **not** as a 429 mitigation. Do not let a 5,000-token threshold silently force RAG.
- **Tier 3 (Map-Reduce)** — trigger **only** when the student's raw submission alone exceeds the model's actual **context-window limit** (a `400`-class context error), not the 5,000-token rate threshold. This is a genuinely different, much rarer condition.
- Remove/raise the `CONTEXT_BUDGET_TOKENS = 5000` rate-driven routing trigger. Replace it with a model-context-window check (e.g. trigger Tier 3 only above ~80–90% of the model's max context).

---

## 3. Implementation steps (ordered)

1. Add `rate_limiter.py` (section 2.1). Ensure Redis is reachable from all workers.
2. In `ResilientLLM` (`llm_provider.py`): call `acquire_slot()` before each request; call `update_from_headers(resp.headers)` after each response; replace fixed backoff with `_sleep_before_retry` (section 2.2).
3. Set Celery LLM-task concurrency to 2–3, or add a shared semaphore at the call site (section 2.3).
4. In `router.py`: default to Tier 0; change the Tier 3 trigger from the 5,000-token rate threshold to a model-context-window overflow check; demote Tier 2/RAG from "429 fix" to "optional optimization" (section 2.4).
5. Run the discovery probe (section 4) to read the real ceiling, then set `RPM_KEY`/`FALLBACK_RPM` accordingly.
6. Validate against acceptance criteria (section 5).

---

## 4. Discovering the real RPM ceiling

Run once **while workers are idle** (this consumes one request against the quota and `ratelimit-remaining` reflects concurrent load):

```python
import httpx, os

resp = httpx.post(
    "https://inference.do-ai.run/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['DO_TOKEN']}"},
    json={"model": "your-model-name",
          "messages": [{"role": "user", "content": "ping"}],
          "max_tokens": 1},
    timeout=30,
)
for h in ("ratelimit-limit", "ratelimit-remaining", "ratelimit-reset", "retry-after"):
    print(h, "->", resp.headers.get(h))
```

Probe the **actual model and token the workers use** — limits are per-token and can vary per model. Set the limiter's effective per-minute target ~10–20% below the observed binding limit.

---

## 5. Acceptance criteria

- A batch of 4+ concurrent submissions completes with **zero `429`-induced failures**.
- No request is sent while the shared in-window count is at/above `RPM_LIMIT × SAFETY_FACTOR`.
- On a forced `429`, the worker waits for `retry-after` (+ jitter), not a fixed schedule, and succeeds on retry.
- Grading output for a standard submission is produced by **Tier 0 (full context)**, not RAG or Map-Reduce.
- Tier 3 fires only for submissions exceeding the model context window, not for ordinary large-but-in-window inputs.

---

## 6. Optional higher-leverage path: Batch Inference API

Grading is asynchronous (no user waiting on latency), which makes it a strong fit for DigitalOcean's **Batch Inference API**: upload a JSONL of all grading requests, let DO meter them server-side, and collect results when complete. This eliminates client-side RPM management entirely while preserving full-context (Tier 0) quality per submission. Recommended as a parallel pilot for bulk/scheduled grading runs.
Reference: https://docs.digitalocean.com/reference/api/reference/batch-inference/

Also worth doing in parallel: request a quota increase on the **Resource Limits** page in the DigitalOcean control panel (routers support up to 1,000 RPM vs. the 250 default).

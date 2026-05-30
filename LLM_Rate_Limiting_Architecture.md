# AI Grading Pipeline: Overcoming Token Limits & Rate Limiting

## 1. The Problem: The "Context Stuffing" Bottleneck

During the live deployment of the GradeWise AI feedback system, we encountered a critical failure when attempting to grade student submissions. The system threw repeated **HTTP 429 Too Many Requests** errors.

### The Logs
```text
worker-1  | [2026-05-30 16:05:22,833] Routing payload: est_tokens=13201, has_structure=False
worker-1  | [2026-05-30 16:05:22,833] Decision: Tier 0 (Context Stuffing)
worker-1  | [2026-05-30 16:05:22,833] Executing Tier 0 grading for [...]_Amna stqa.pdf
worker-1  | [2026-05-30 16:05:24,515] HTTP Request: POST https://inference.do-ai.run/v1/chat/completions "HTTP/1.1 429 Too Many Requests"
worker-1  | [2026-05-30 16:05:24,516] WARNING/ForkPoolWorker-4] LLM chat retry: provider=gradient attempt=1 backoff=0.50s err=Client error '429 Too Many Requests'
worker-1  | [2026-05-30 16:05:28,993] ERROR/ForkPoolWorker-4] Grading failed: Client error '429 Too Many Requests'
```

### Why Did This Happen?
We are using **DigitalOcean's Inference API** to power the Large Language Models (LLMs) running our grading pipeline. Like most AI providers, DigitalOcean imposes strict limits on **Tokens Per Minute (TPM)** and **Requests Per Minute (RPM)**.

Initially, our grading architecture defaulted to **Tier 0 (Context Stuffing)**. This tier takes the *entire* text of the student's submission (e.g., a 17,700-character PDF), combines it with the *entire* Master Reference Document, and attaches the grading rubric. 

In the logs above, this combined payload was estimated at **13,201 tokens**. Sending a massive 13,000+ token payload in a single HTTP request instantly exhausted the DigitalOcean API rate limit quota, causing the server to immediately reject the request with a `429 Too Many Requests` status code. 

Furthermore, because our Celery background worker is highly concurrent (processing 4 submissions simultaneously), a batch upload of 4 files would blast the API with four simultaneous 13,000-token requests, virtually guaranteeing a rate-limit block.

---

## 2. The Solutions: Evolving the Architecture

To solve this, we discussed and implemented three distinct architectural strategies to ensure the platform scales without hitting provider limits.

### Strategy 1: Exponential Backoff & Resiliency (The Safety Net)
The first step was preventing a hard failure when a rate limit is hit. We modified the `ResilientLLM` provider wrapper (`llm_provider.py`) to catch `429` errors and implement an **Exponential Backoff algorithm**. 

Instead of failing immediately, the worker now pauses and retries up to 6 times, waiting progressively longer (2s, 4s, 8s, 16s, 32s, 64s) until the API provider resets the quota for the next minute.
* **Result:** The system gracefully absorbs temporary rate limit spikes without dropping student submissions.

### Strategy 2: Lowering the Context Budget & Triggering RAG (Tier 2)
While backoff is great, we needed to reduce the sheer size of the payloads. We have a robust **Retrieval-Augmented Generation (RAG)** pipeline built-in (**Tier 2**), but it wasn't triggering because the `CONTEXT_BUDGET_TOKENS` threshold was set too high (200,000 tokens).

We drastically lowered this threshold to `5,000` tokens. Now, if the combined token count of a submission and its reference material exceeds 5,000 tokens, the "Routing Ladder" intelligently intercepts the payload and kicks it down to Tier 2. 

In Tier 2, the system completely strips out the massive Master Reference Document. Instead, it embeds the grading rubric criteria, searches the PostgreSQL Vector database (`pgvector`), and retrieves only the 2-3 most relevant paragraphs. 
* **Result:** The token payload shrinks from 13,000+ tokens to roughly 5,500 tokens, easily bypassing the 429 limits.

### Strategy 3: Map-Reduce Grading for Massive Essays (Tier 3)
*The Professor's Edge Case:* What if a student submits a 50-page creative writing essay? In this scenario, there is no "Reference Document" to strip out using RAG; the AI *must* read all 50 pages of the student's original work. 

To solve this, we architected and built a brand new grading tier: **Tier 3 (Map-Reduce)**.
If the student's raw submission alone exceeds the 5,000 token budget, the router hands it to Tier 3. 
1. **Map (Chunking):** The system slices the massive 50-page essay into digestible chunks (e.g., 4 pages per chunk).
2. **Paced Evaluation:** It sends Chunk 1 to the LLM. Once complete, it intentionally triggers an `asyncio.sleep()` cooldown delay before sending Chunk 2, successfully bypassing the Tokens Per Minute limit by spreading the grading out over several minutes.
3. **Reduce (Synthesis):** Once all chunks are evaluated, the system averages the numerical scores and concatenates the feedback sequentially into a single unified report.
* **Result:** The platform can now successfully ingest, process, and grade submissions of infinite length without ever crashing the AI API limits.

---

## 3. Current Architecture: The Routing Ladder

To visualize how the token problem is now managed dynamically, here is the current architecture of our AI Dispatch Router (`router.py`):

1. **Ingestion:** Submission text and Reference text are extracted. `est_tokens` is calculated.
2. **Router Decision Matrix:**
   - **`If student_tokens > 5,000:`** Route to **Tier 3 (Map-Reduce)** to chunk the student's massive document and grade it iteratively with cooldowns.
   - **`If combined_tokens <= 5,000:`** Route to **Tier 0 (Context Stuffing)** for fast, cheap grading inside a single prompt.
   - **`If reference_has_structure:`** Route to **Tier 1 (Tree Navigation)** to dynamically walk the document tree (e.g., Markdown headers).
   - **`Else:`** Route to **Tier 2 (Vector Fallback)** to use pgvector RAG, retrieving only the semantic paragraphs required to grade the rubric.

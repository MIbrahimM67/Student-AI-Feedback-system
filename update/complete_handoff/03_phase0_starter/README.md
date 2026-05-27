# Phase 0 Starter — AI Feedback System

This is the **foundation** for the build described in v3 + the production addendum.
It is intentionally minimal: one Postgres (with pgvector and the relational
knowledge-graph tables), Redis, FastAPI, a Celery worker, a provider-agnostic
LLM service, and an evaluation harness skeleton. Everything else (the routes,
the pipeline, the UI) is built *on top of this* in later phases.

## Why this exists as a separate starter

The two things that AntiGravity tends to get wrong without explicit scaffolding
are (a) the Postgres extensions + Row-Level Security wiring and (b) the
provider-agnostic LLM abstraction with retries/failover. Both are baked in
here so the rest of the build starts from a correct, production-shaped base.

## Bring it up

```bash
cp .env.example .env
# fill in: POSTGRES_PASSWORD, APP_USER_PASSWORD, GRADIENT_API_KEY,
# GRADIENT_BASE_URL, FIREBASE_* values.

docker compose up -d
docker compose logs -f api    # watch for "Application startup complete"
```

## Phase 0 acceptance check

These must all pass before Phase 1.

1. **Health endpoint responds.**
   ```bash
   curl -s http://localhost:8000/health | jq
   ```
   Expect `{"status":"ok","postgres":"ok","redis":"ok"}`.

2. **pgvector extension is loaded.**
   ```bash
   docker compose exec postgres psql -U feedback -d feedback \
     -c "SELECT extname FROM pg_extension WHERE extname='vector';"
   ```
   Expect one row: `vector`.

3. **Vector embed round-trip works.**
   ```bash
   curl -s -X POST http://localhost:8000/_debug/embed \
        -H "Content-Type: application/json" \
        -d '{"text":"hello world"}' | jq '.dim, .preview'
   ```
   Expect a 1024-dim vector (BGE-M3) and a numeric preview.

4. **RLS is enforced** (the most important check — protects every customer's data).
   Use the test script:
   ```bash
   docker compose exec postgres psql -U app_user -d feedback -f /docker-entrypoint-initdb.d/rls_test.sql
   ```
   *(Or, manually: create two orgs, insert a row in `subjects` under org A,
   then `SET app.current_org_id = '<org B uuid>'` and `SELECT * FROM subjects` —
   you must get zero rows.)*

5. **Eval harness runs against the example golden set.**
   ```bash
   docker compose exec api python -m eval.run_eval --golden eval/golden_set.example.jsonl
   ```
   Expect a printed report. The stubbed grader returns perfect agreement
   (it's a placeholder); the real grader is wired in during Phase 6.

If all five pass, the foundation is correct. Move to Phase 1 in v3 §14.

## What is intentionally *not* here

These are AntiGravity's job in later phases:
- API routes beyond `/health` and the embed debug endpoint.
- The grading pipeline (Specialist → Judge → Senior). The `llm_provider` is the
  building block; the pipeline composes it with retrieval + the graph + scoring.
- The UI.
- Real payments (Phase: post-MVP; Pakistan-first via Payfast, global via Paddle).
- Production hardening (see the addendum): managed Postgres, gVisor/Firecracker
  sandbox, full observability, autoscaling.

## File map

```
phase0_starter/
├── README.md                                this file
├── docker-compose.yml                       services: postgres, redis, api, worker
├── .env.example                             copy to .env and fill in
├── postgres/
│   └── init.sql                             EXTENSIONS + tables + HNSW + RLS policies
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                          FastAPI + /health + /_debug/embed
│       └── services/
│           └── llm_provider.py              provider-agnostic LLM (chat/embed/rerank + failover)
└── eval/
    ├── run_eval.py                          golden-set evaluation harness
    └── golden_set.example.jsonl             two example records to start the golden set
```

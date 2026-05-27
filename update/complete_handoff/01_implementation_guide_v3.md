# Implementation Guide v3 — AI-Powered Feedback System for Student Assignments

**For:** Muhammad Ibrahim — FYP, Department of Computer Science, Quaid-e-Azam University
**Build agent:** Google Antigravity (agentic IDE)
**Supersedes:** v1 and v2. The headline change from v2: **one database (Postgres) does everything** — relational data, vector RAG (pgvector), and the knowledge graph (Apache AGE).

> **How to read this.** Sections 0–4 explain the *decisions and architecture* (read these yourself). Sections 5+ are the *build spec* for Antigravity. Section 18 is the master prompt you paste to start the build.
>
> **Note on figures.** Model names, prices, credit amounts, and free-tier limits were correct as of the research date but change often. Re-verify the DigitalOcean model catalogue and the GitHub Student Pack before building.

---

## 0. The core idea in one paragraph

A student or instructor submits an assignment. Before any AI grades it, the system **retrieves the relevant passages from the instructor's own reference material** (vector search) and **looks up which concepts the question is testing** (knowledge graph). The AI then grades *only against that evidence and the rubric*, citing the exact passage behind every judgement. A second AI verifies the first. The rubric total is summed in code, not by the AI. Anything the AI isn't confident about is flagged for the instructor. The result is feedback that is **grounded, verifiable, consistent, and fast** — not "magic," and not a model guessing from memory.

**Everything lives in one Postgres database**, which is what makes it fast (one round-trip), consistent (one source of truth), and cheap (no extra services).

---

## 1. The honest reliability model (state this in your report)

Do **not** claim "100% accuracy." Claim this instead, and you'll defend it easily in the viva:

> The system does not claim perfect grades. It claims **grounded, verifiable, and consistent** feedback. Every factual statement the AI makes is traced to (a) a retrieved passage from the instructor's reference material, (b) the actual result of executing the student's code, or (c) a rubric score computed deterministically from per-criterion judgements. Low-confidence judgements are flagged for human review, keeping the instructor in the loop.

Four pillars make this true in code:

1. **Retrieval grounding (RAG).** Relevant reference passages + expected concepts are fetched *before* the LLM runs. Prompt rule: *"Judge only against the provided context and rubric; if the reference doesn't cover something, say so — don't assume."*
2. **Verification.** A second, *different* model checks the first model's claims against the same context.
3. **Determinism where it belongs.** Rubric totals summed in Python. Code actually executed. JSON schema-validated. Identical inputs cached.
4. **Confidence + human-in-the-loop.** Low-confidence or disputed items become `needs_review` instead of a silent grade.

This is also the latency answer: retrieval is milliseconds; the LLM is the slow part. You cut *felt* latency with background jobs + streaming status, and *repeat* latency with caching. "Zero latency" isn't a real target; "fast and predictable" is.

---

## 2. One database, three jobs (the architecture decision)

Everything structured lives in **PostgreSQL**, using two extensions:

| Job | How Postgres does it | Why here |
| --- | --- | --- |
| **Relational data** (users, subjects, references, assignments, submissions, reports, warnings) | Normal tables | ACID, the data is naturally relational. |
| **Vector RAG** (semantic search over reference text) | **pgvector** extension (HNSW index) | The vectors live next to the metadata, so one filtered query does subject-scoping + similarity search together. Milliseconds at FYP scale and far beyond. |
| **Knowledge graph** (curriculum structure) | **Apache AGE** extension (openCypher) | Real graph queries in the same DB. *(Fallback: model the same edges as plain tables — identical grading benefit, zero extra setup.)* |

**Where vector vs. graph applies:**
- **Vector (pgvector):** unstructured text → semantic similarity. The instructor's textbook chunks, model answers, lecture notes; student-submission chunks (for plagiarism).
- **Graph (AGE):** structured relationships → reasoning + explainability. *What a question tests*, *which rubric criterion maps to which concept*, *common misconceptions*. The graph tells the grader what to look for **before** any LLM call; the vectors supply the evidence.
- **The bridge:** each vector chunk stores the `concept_ids` it explains, matching the concept ids in the graph. Graph for structure, vectors for evidence — together this is the **HybridRAG** pattern (references at the end).

**Knowledge-graph scope for this FYP (decided — keep it minimal):**
- ✅ `Question → EXPECTS → Concept`
- ✅ `RubricCriterion → ASSESSES → Concept`
- ✅ `Concept → COMMON_MISTAKE → Misconception`
- ❌ prerequisite / related-concept webs — skip; high effort, low demo payoff.

---

## 3. Hosting & credits plan

**GitHub Student Pack correction:** the pack includes **DigitalOcean ($200/yr)** and **Azure for Students ($100, no card)** — **not AWS.** Re-check the pack page, but plan around DO + Azure.

**Consolidate on DigitalOcean; don't split the live request path across clouds** (cross-cloud hops add latency — the opposite of your goal).

| Layer | Where | Cost | Notes |
| --- | --- | --- | --- |
| Frontend (Next.js) | **Vercel** Hobby | Free | Best Next.js host. |
| Sign-in (Google OAuth) | **Firebase Auth** | Free | Keep — trivial and already in your docs. |
| File storage (uploads, PDFs) | **Firebase Storage** | Free | Keep. (Alt: DO Spaces if you want everything on DO.) |
| **All structured data + vectors + graph** | **PostgreSQL** (pgvector + Apache AGE) in the Droplet's Docker Compose | Free (uses droplet) | The heart of the system. |
| Backend API + workers + sandbox | **DigitalOcean Droplet** (Docker Compose) | ~$18–24/mo from the $200 | FastAPI + Celery + Redis + Postgres + code-sandbox, co-located = low latency. |
| LLM inference + embeddings + rerank | **DigitalOcean Gradient** (serverless) | Pay-per-token, ~cents | Section 4. |
| Spare credit | **Azure $100** | Reserve | Or move Postgres to a managed Azure DB later for backups/HA. |

> **Production upgrade path (optional):** swap the in-droplet Postgres for **DigitalOcean Managed PostgreSQL** (~$15/mo) to get automated backups + HA. Managed DO Postgres supports pgvector; if it doesn't support Apache AGE in your region, keep the graph as relational tables (see §2 fallback). For the FYP demo, in-droplet Postgres is simplest and fastest.
>
> **The only real money risk:** idle infra left running. Set a billing alert at $50. Tear down anything you're not demoing.

---

## 4. Model selection on DigitalOcean Gradient (performance-first)

**Accuracy and consistency come mostly from the pipeline, not the model** — grounding + reranking + verification + deterministic scoring do more than model size. Within that pipeline, these are fast *and* strong picks. Prices per **1M tokens (in / out)** as of the research date — **re-verify in the Model Catalogue.**

| Job | Model | Price (in/out) | Why |
| --- | --- | --- | --- |
| **Specialist** (deep analysis + first-pass grade) | `gpt-oss-120b` | $0.10 / $0.70 | MoE → fast inference *and* strong reasoning. Step-up if you want max reasoning: `Qwen 3.5 397B A17B` ($0.55/$3.50) or `GLM 5` ($1.00/$3.20) — still cents/assignment. |
| **Judge** (verify, temp 0) — *different family on purpose* | `Qwen3-32B` | $0.25 / $0.55 | A different family doesn't share the Specialist's blind spots. Alt: `Llama 3.3 70B`. |
| **Senior** (format + strict JSON only) | `gpt-oss-120b` | $0.10 / $0.70 | Low temp; rewrites, doesn't re-grade. |
| **Utility** (name extraction, sensitive-data flag, query rewrite, concept extraction) | `gpt-oss-20b` | $0.05 / $0.45 | Tiny + fast for easy tasks. Alt: `Gemma 4`. |
| **Embeddings** (RAG + plagiarism) | `BGE-M3` | $0.02 / 1M | Multilingual, strong retrieval. |
| **Reranker** (precision on retrieved chunks) | `BGE Reranker v2 m3` | $0.01 / 1M | Biggest cheap win for retrieval accuracy. |
| **Handwriting OCR** (optional upgrade) | a vision model, e.g. `Nemotron Nano 12B v2 VL` | $0.20 / $0.60 | Reads messy handwriting far better than Tesseract (keep Tesseract as free baseline). |

**Cost reality:** a full Specialist→Judge→Senior run ≈ 60k input + 12k output tokens ≈ **$0.014 per assignment** on `gpt-oss-120b`. A 30-file batch ≈ **$0.45**. Your $200 credit grades tens of thousands. **Token cost is not a concern.**

**Speed levers (since you want faster):**
- Retrieve for all questions of a submission **in parallel**.
- Grade batch submissions **concurrently** across Celery workers.
- **Cache** by `hash(submission + assignment_version)` — identical input returns instantly.
- pgvector is **co-located** with the data → retrieval is a local query, not a network call.
- *(Optional, advanced)* skip the Judge call when Specialist confidence is very high across all criteria — saves one LLM round-trip on easy submissions.

---

## 5. Postgres schema

Keep Firebase **Auth** (Google sign-in) and **Storage** (files). Everything below is Postgres. Use Firebase `uid` as the user key.

### 5.1 Core relational tables (abridged — Antigravity to expand with constraints/indexes)
```sql
users(uid PK, email, display_name, photo_url, role,            -- student|instructor|admin
      faculty_status, pro_status, warning_count, blocked_until, created_at, updated_at)

instructor_profiles(uid PK FK->users, department, designation, institution,
      teaching_level, default_language, grading_style, created_at, updated_at)

faculty_applications(id PK, user_id FK, full_name, university, department, designation,
      official_email, proof_file_url, status, rejection_reason, reviewed_by, created_at, reviewed_at)

subjects(id PK, instructor_id FK, code, title, description, level, language,
      kb_status,                       -- empty|indexing|ready
      reference_count, assignment_count, created_at, updated_at)

reference_materials(id PK, subject_id FK, title, type,   -- textbook|lecture_notes|marking_scheme|model_answer|slides
      file_url, index_status, chunk_count, created_at)    -- pending|chunking|embedded|failed

assignments(id PK, subject_id FK, title, plagiarism_enabled, version, created_at)
questions(id PK, assignment_id FK, text, max_marks)
rubric_criteria(id PK, assignment_id FK, name, max_score, description)

submissions(id PK, user_id FK, assignment_id FK NULL, subject_id FK NULL, batch_id FK NULL,
      type, mode, input_text, file_url, file_name, status, feedback_report_id, created_at)

batch_jobs(id PK, instructor_id FK, subject_id FK, assignment_id FK, plagiarism_enabled,
      status, total_files, processed_files, export_excel_url, export_zip_url, created_at)

feedback_reports(id PK, submission_id FK, batch_id FK NULL, student_name,
      overall_score, max_score, status, summary,
      strengths JSONB, weaknesses JSONB, suggestions JSONB,
      rubric_scores JSONB,             -- includes per-criterion confidence + citations
      specialist_output JSONB, judge_output JSONB, senior_output JSONB,
      pdf_url, created_at)

plagiarism_reports(id PK, submission_id FK, batch_id FK, similarity_score, matches JSONB, created_at)
warnings(id PK, user_id FK, submission_id FK, reason, severity, status, created_at, dismissed_by)
audit_logs(id PK, actor_uid, action, target, meta JSONB, created_at)
```

### 5.2 Vectors — **pgvector**
```sql
CREATE EXTENSION IF NOT EXISTS vector;

reference_chunks(
  id PK,
  subject_id FK,                 -- ALWAYS filter on this (per-subject scoping)
  reference_id FK,
  doc_type,                      -- textbook|model_answer|...
  concept_ids TEXT[],            -- bridge to the graph
  chunk_index INT,
  text TEXT,
  embedding vector(1024)         -- BGE-M3 dimension
);
CREATE INDEX ON reference_chunks USING hnsw (embedding vector_cosine_ops);

submission_chunks(            -- for plagiarism
  id PK, submission_id FK, batch_id FK, chunk_index INT, text TEXT, embedding vector(1024)
);
CREATE INDEX ON submission_chunks USING hnsw (embedding vector_cosine_ops);
```
Retrieval query pattern: `WHERE subject_id = :sid ORDER BY embedding <=> :query_vec LIMIT 20`, then rerank.

### 5.3 Knowledge graph — **Apache AGE** (one graph per database, nodes namespaced by `subject_id`)
**Nodes:** `Concept{concept_id, name, definition, subject_id}`, `Question{question_id}`, `RubricCriterion{criterion_id}`, `Misconception{misconception_id, text}`.
**Edges:**
```
(Question)-[:EXPECTS]->(Concept)
(RubricCriterion)-[:ASSESSES]->(Concept)
(Concept)-[:COMMON_MISTAKE]->(Misconception)
```
`Concept.concept_id` matches `reference_chunks.concept_ids` — the entity-linking bridge.

> **Fallback if AGE is fiddly:** create `concepts`, `question_concepts`, `rubric_concepts`, `concept_misconceptions` as plain tables. Grading accuracy is identical; you only lose the Cypher syntax.

---

## 6. Knowledge-base build (background indexing job)

Runs when an instructor uploads references to a subject:
```
1. Upload reference file(s) to the Subject → Firebase Storage.
2. Worker downloads, extracts text (PDF/DOCX → text; scanned → OCR).
3. Chunk: section-based or semantic, ~512–1024 tokens, ~15% overlap.
4. Embed each chunk via Gradient BGE-M3.
5. Concept extraction (utility LLM, cheap): per chunk, list the concepts it explains
   → upsert Concept nodes (AGE) → tag the chunk's concept_ids.
6. Insert chunks + embeddings + concept_ids into reference_chunks (pgvector).
7. Mark reference index_status='embedded'; when all done, subject.kb_status='ready'.
```
When an instructor **creates an assignment**, a light job parses each question + rubric criterion (utility LLM) and creates `Question-[:EXPECTS]->Concept` and `RubricCriterion-[:ASSESSES]->Concept` edges. The instructor reviews/edits these on the concept-map screen — the human-in-the-loop quality gate.

---

## 7. The hardened grading pipeline (per submission)

`[D]` = deterministic, `[LLM]` = model call.
```
[D]  0. Cache check: hash(submission + assignment.version). Hit → return cached report.
[D]  1. Extract text (OCR if needed). If coding type → run in Docker sandbox, capture output/errors.
[D]  2. Sensitive-data scan (regex + cheap utility LLM) → raise warning if triggered.
[D]  3. Graph lookup (AGE): per question → EXPECTS concepts; rubric criteria that ASSESS them;
        each concept's COMMON_MISTAKE list.
[D]  4. Retrieve (pgvector): per (question, student-answer), filter subject_id → top-20 by cosine
        → rerank (BGE Reranker) → keep top-6. Also pull chunks for the expected concept_ids.
        (Run all questions' retrievals in parallel.)
[LLM] 5. SPECIALIST (gpt-oss-120b): given question + rubric + expected concepts + retrieved context
        + misconceptions + student answer (+ code results) → per-criterion judgement, confidence,
        and cited chunk_ids. Rule: "Use only the provided context; cite a chunk_id for every claim;
        if context doesn't support it, return needs_review for that criterion."
[LLM] 6. JUDGE (qwen3-32b, temp 0): re-check Specialist's claims vs the SAME context; flag
        unsupported claims / inconsistent scoring; output corrections + agreement flag.
[D]  7. Reconcile: apply Judge corrections; SUM rubric scores in Python; low confidence OR
        Specialist/Judge disagreement → criterion status 'needs_review'.
[LLM] 8. SENIOR (low temp): turn the reconciled result into student-friendly prose + strict JSON.
        Formats only — never re-grades.
[D]  9. Validate JSON (Pydantic); one repair retry on failure, else mark failed.
[D] 10. Persist feedback_report; cache; generate PDF.
```

**Final feedback JSON (Pydantic-validated):**
```json
{
  "overallScore": 0, "maxScore": 0,
  "status": "pass | fail | needs_review",
  "summary": "string",
  "strengths": ["string"], "weaknesses": ["string"], "suggestions": ["string"],
  "rubricScores": [
    { "criterion": "string", "score": 0, "maxScore": 10,
      "confidence": 0.0, "justification": "string", "citations": ["chunk_id"] }
  ],
  "finalComments": "string"
}
```
Steps 0,1,2,3,4,7,9,10 are deterministic — that's the answer to "we can't rely on LLM calls all the time." The LLM only reads, reasons, and writes, always against retrieved evidence.

---

## 8. Plagiarism (reuses the same pgvector infra)
```
1. Chunk + embed the submission → submission_chunks.
2. Internal similarity (cheap, high-signal, do this first): cosine vs (a) other submissions in the
   batch, (b) the subject's reference/model-answer chunks. Catches copying from classmates and from
   the provided material — the two common real cases — with no web calls.
3. External (optional): generate queries from the prompt → fetch 5–10 web sources → embed → compare.
   Keep it a "similarity assistant," not a Turnitin clone (say so in the report).
4. Store top matches + similarity % in plagiarism_reports.
```

---

## 9. OCR & code execution
- **OCR:** Tesseract baseline (free); optional vision-model path on Gradient for handwriting.
- **Code sandbox (strict):** Python/Java/C++ only; per-execution Docker container; **no network; 5s timeout; 256MB; max output size; container destroyed after run; never run on host.** Real execution result feeds pipeline step 1.

---

## 10. Backend structure
```
backend/app/
  main.py  config.py
  auth/firebase.py                 # verify Firebase ID tokens
  db/
    postgres.py                    # connection pool (asyncpg / SQLAlchemy)
    vectors.py                     # pgvector queries (search, upsert)
    graph.py                       # Apache AGE Cypher queries (or relational fallback)
    cache.py                       # redis result cache
  api/
    auth_routes.py student_routes.py instructor_routes.py admin_routes.py report_routes.py
    subject_routes.py reference_routes.py assignment_routes.py    # NEW
  services/
    gradient_service.py            # chat() + embed() + rerank()
    retrieval_service.py           # hybrid search + rerank + subject filter (NEW)
    graph_service.py               # build/query the graph (NEW)
    indexing_service.py            # chunk → embed → concept-extract → insert (NEW)
    feedback_pipeline.py           # Section 7
    ocr_service.py file_service.py plagiarism_service.py grading_service.py
    report_service.py warning_service.py code_sandbox_service.py
  models/                          # Pydantic incl. strict feedback schema
  workers/  celery_app.py  tasks.py   # indexing job, batch grading job
  utils/  validators.py security.py prompt_templates.py chunking.py pdf_templates.py
```
`docker-compose.yml` on the Droplet: `api` (FastAPI), `worker` (Celery), `redis`, `postgres` (image with pgvector **and** Apache AGE — e.g. base on `apache/age` and add pgvector, or a Postgres image with both extensions), `sandbox` base image.

---

## 11. API endpoints (additions to v1)
```
GET/PUT  /api/instructor/profile

POST     /api/subjects                       GET /api/subjects     GET/DELETE /api/subjects/{id}
POST     /api/subjects/{id}/references        GET /api/subjects/{id}/references
GET      /api/subjects/{id}/kb-status         DELETE /api/references/{id}

POST     /api/subjects/{id}/assignments       GET /api/subjects/{id}/assignments
GET/PUT  /api/assignments/{id}/concept-map    # review/edit Question→Concept, Rubric→Concept

POST     /api/assignments/{id}/batch          # batch upload bound to this assignment
GET      /api/instructor/batch/{id}
POST     /api/instructor/batch/{id}/confirm-names
POST     /api/instructor/batch/{id}/process
GET      /api/instructor/batch/{id}/export
```

---

## 12. Frontend structure
```
frontend/app/
  (public)/ landing, login, role-selection
  student/  dashboard, submit, feedback/[id]
  instructor/
    dashboard/  profile/                       # teaching profile
    subjects/                                    # the "Classes" view
    subjects/[id]/  (references + assignments tabs)
    subjects/[id]/references/                     # upload + KB status
    subjects/[id]/assignments/
    assignments/[id]/concept-map/                 # editable graph
    assignments/[id]/batch/   batch/[id]/
  admin/  dashboard, applications, users, warnings
```

---

## 13. UI / design system — making it *not* generic

The look you want (Claude's interface, 21st.dev) is **calm, editorial, content-first** — not a stock SaaS template.

**Shell.** Persistent **collapsible left sidebar** as primary nav, like Claude. Start from the shadcn **`sidebar` block** (`sidebar-07` collapsible-icon) and restyle. Sidebar holds: subject switcher (subjects = your "workspaces"/Teams classes), primary nav, user menu pinned to the bottom.

**Palette (warm, restrained).** Warm off-white / light sand background (not pure white), near-black ink, barely-there warm-grey cards with **hairline borders** over heavy shadows, **one** restrained accent (muted terracotta *or* deep indigo — pick one, use sparingly), warm-charcoal dark mode. Generate/tune the exact tokens with **tweakcn** so it's a system, not random hex.

**Type.** **Serif display** for headings/landing + clean grotesque (Inter/Geist) for body/UI. This pairing is most of why a UI reads as "designed."

**Motion.** Framer Motion, subtle: 150–250ms ease; content fades/slides; skeleton loaders during AI processing; streaming reveal for feedback. No bounce/overshoot in a grading tool.

**Components (all shadcn-compatible; install via `npx shadcn@latest add "<url>"`):**
- **shadcn/ui** — base (sidebar, table, dialog, form, badge, progress, tabs, card).
- **21st.dev** — curated community blocks (hero, pricing, fancy upload dropzones, animated stats). MIT, copy-paste.
- **Origin UI / Kibo UI** — polished form/table/upload primitives.
- **Aceternity / Magic UI** — landing page only; keep out of the dashboards.

**Signature screens (your "designed, not templated" proof):**
- **Subject home** = the "class" view: references with KB-status pills (`indexing…`/`ready`), assignment cards, a concept-map preview.
- **Feedback report** = a reading view, not a form dump: score as a quiet ring, strengths/weaknesses as annotated cards, and **citations that expand to show the exact reference passage** the AI grounded its judgement on. This is your demo "wow" and your credibility proof.
- **Concept-map editor** = a simple `react-flow` graph of `Question → Concept → Rubric`, editable. Makes examiners believe the knowledge graph is real.

---

## 14. Build order (phased, with acceptance checks)
```
Phase 0 — Foundations
  Firebase Auth + Storage; Next.js + Tailwind + shadcn; FastAPI; docker-compose
  (api, worker, redis, postgres[pgvector+AGE], sandbox); Gradient key wired.
  ✓ health OK; can embed a test string; pgvector + AGE extensions load; CREATE a test vector + node.

Phase 1 — Auth & roles
  Google sign-in, role selection, users table, RBAC middleware.
  ✓ three roles → three dashboards; protected routes reject wrong roles.

Phase 2 — Instructor profile + Subjects
  Profile CRUD; create/list subjects; subject home shell.
  ✓ instructor creates "OOP" subject; it appears in the sidebar.

Phase 3 — Reference upload + indexing
  Upload → job: extract → chunk → embed → concept-extract → insert reference_chunks + AGE Concept nodes.
  ✓ kb_status empty→indexing→ready; reference_chunks has rows scoped by subject_id;
    AGE shows Concept nodes; chunks carry concept_ids.

Phase 4 — Retrieval service
  pgvector search + BGE rerank + subject filter; a debug endpoint returning top chunks.
  ✓ querying "polymorphism" in OOP returns relevant, reranked passages.

Phase 5 — Assignments + concept-map
  Create assignment (parse → EXPECTS / ASSESSES edges); editable concept-map screen.
  ✓ each question shows its expected concepts; instructor can correct them.

Phase 6 — Single-submission grading (hardened pipeline)
  Student submit → pipeline (§7) → strict JSON → feedback reading view with expandable citations.
  ✓ every justification has a citation OR is needs_review; rubric total == Python sum.

Phase 7 — Code sandbox + OCR
  ✓ a buggy program is graded against its real runtime error; a handwritten scan is read.

Phase 8 — Faculty verification, Pro, Admin
  ✓ locked features unlock only after approval + Pro.

Phase 9 — Batch (bound to assignment) + name editing + exports
  ✓ 30-file batch completes via workers; Excel / Excel+PDF zip contain scores, summaries, plagiarism %, PDF links.

Phase 10 — Plagiarism (internal first, web optional)
  ✓ a submission copied from a classmate shows high internal similarity.

Phase 11 — UI polish + design pass
  Sidebar shell, tweakcn tokens, citation-reveal, concept-map viz, skeleton loaders.
  ✓ doesn't look like a stock template.

Phase 12 — Hardening + deploy
  Caching, rate limits, billing alert, retries, error states; deploy (Vercel + Droplet).
  ✓ identical submission returns cached result instantly; idle cost bounded.
```

---

## 15. Environment variables
```env
# Firebase (auth + storage only)
FIREBASE_PROJECT_ID=  FIREBASE_CLIENT_EMAIL=  FIREBASE_PRIVATE_KEY=  FIREBASE_STORAGE_BUCKET=

# Postgres (relational + pgvector + Apache AGE)
DATABASE_URL=postgresql://user:pass@postgres:5432/feedback

# DigitalOcean Gradient
GRADIENT_API_KEY=  GRADIENT_BASE_URL=
GRADIENT_MODEL_SPECIALIST=gpt-oss-120b
GRADIENT_MODEL_JUDGE=qwen3-32b
GRADIENT_MODEL_SENIOR=gpt-oss-120b
GRADIENT_MODEL_UTILITY=gpt-oss-20b
GRADIENT_EMBED_MODEL=bge-m3
GRADIENT_RERANK_MODEL=bge-reranker-v2-m3
GRADIENT_VISION_OCR_MODEL=        # optional

# Jobs / cache
REDIS_URL=redis://redis:6379/0

# Limits
STUDENT_MAX_FILE_MB=1  INSTRUCTOR_BATCH_MAX_FILES=30  INSTRUCTOR_BATCH_MAX_MB=100
SANDBOX_TIMEOUT_SECONDS=5  SANDBOX_MEMORY_MB=256
```
Never expose any of these to the frontend.

---

## 16. Prompt design rules (`prompt_templates.py`)
- **Specialist & Judge prompts include:** instructor profile, subject title/level, the question, rubric criteria + max scores, expected concepts, common misconceptions, retrieved chunks (each with `chunk_id`), student answer (+ code results).
- **Grounding rule (verbatim in system prompt):** *"Evaluate only against the provided reference context and rubric. Cite the chunk_id behind every factual claim. If the context does not support a judgement, set that criterion to needs_review rather than guessing."*
- **Judge** = different model, temp ≈ 0. **Senior** never changes scores. **All JSON** Pydantic-validated, one repair retry.
- Temps: Specialist ≈ 0.2, Judge ≈ 0.0, Senior ≈ 0.3, Utility ≈ 0.0.

---

## 17. For the FYP report
- Frame accuracy honestly (§1) — "grounded + verifiable + human-in-the-loop," never "100%."
- Describe it as **HybridRAG**: pgvector for evidence + Apache AGE knowledge graph for structure, bridged by entity linking. Cite the papers below.
- Justify the part-deterministic pipeline as a *reliability* decision.
- Note the data-layer change from the original SRS/SDD (Firestore → PostgreSQL) and update those documents / inform Dr. Abbasi so the docs stay consistent.

---

## 18. Antigravity Master Prompt
```
You are building a full-stack web app: "AI-Powered Feedback System for Student Assignments".
Follow the phased build order in Section 14; do not skip a phase's acceptance check.

STACK
- Frontend: Next.js 15, React, TypeScript, Tailwind, shadcn/ui, Framer Motion, React Hook Form, Zod,
  Firebase Client SDK (auth). Host on Vercel.
- Backend: Python 3.11+, FastAPI, Celery + Redis, ReportLab (PDF), openpyxl (Excel), Tesseract (OCR),
  Docker code sandbox. Host on a DigitalOcean Droplet via docker-compose.
- ONE DATABASE — PostgreSQL with the pgvector extension (vector RAG) AND the Apache AGE extension
  (knowledge graph). All structured data, all embeddings, and the graph live here.
- Firebase is used ONLY for Google sign-in (Auth) and file storage (Storage).
- AI: DigitalOcean Gradient serverless inference for chat + embeddings + reranking (NEVER expose the key).

ROLES: Student (free, single submissions), Instructor (faculty-verified + Pro: subjects, references,
assignments, batch ≤30 files/100MB, plagiarism, grading, exports), Admin (approvals, Pro, warnings/blocks).

CORE CONCEPTS:
1. SUBJECTS: an instructor creates a subject (e.g. "OOP"), uploads reference materials, and reuses it
   across many assignment batches — like a class in MS Teams.
2. KNOWLEDGE BASE per subject: references are extracted → chunked → embedded (BGE-M3) → concept-extracted
   → stored in reference_chunks (pgvector, filtered by subject_id) and as Concept nodes (Apache AGE).
3. KNOWLEDGE GRAPH (minimal): Question-[:EXPECTS]->Concept, RubricCriterion-[:ASSESSES]->Concept,
   Concept-[:COMMON_MISTAKE]->Misconception. Concept ids in AGE match concept_ids in reference_chunks.
   If Apache AGE is troublesome, model the same edges as plain relational tables — identical behaviour.
4. HARDENED GRADING PIPELINE (deterministic + LLM, see Section 7): cache → extract/run code →
   sensitive scan → graph lookup → pgvector retrieve + rerank → SPECIALIST(gpt-oss-120b) →
   JUDGE(qwen3-32b, temp 0) → deterministic reconcile + SUM scores in Python → SENIOR(format only) →
   Pydantic-validate JSON → persist + PDF. The LLM evaluates ONLY against retrieved context + rubric,
   cites a chunk_id per claim, and returns needs_review when context doesn't support a claim.

DATA: PostgreSQL schema in Section 5 (relational tables, pgvector reference_chunks/submission_chunks,
AGE graph). Final feedback JSON (Pydantic-validated): overallScore, maxScore, status
(pass|fail|needs_review), summary, strengths[], weaknesses[], suggestions[], rubricScores[{criterion,
score, maxScore, confidence, justification, citations[]}], finalComments.

PERFORMANCE: retrieve all questions in parallel; grade batches concurrently across workers; cache by
hash(submission+assignment.version); pgvector co-located for local retrieval.

SECURITY: verify Firebase ID token on every route; RBAC + require_verified_faculty + require_pro;
file/size limits; block users whose blocked_until is in the future; code runs only in isolated Docker
containers (no network, 5s, 256MB, destroyed after run); never run code on the host.

UI (Section 13): persistent collapsible LEFT SIDEBAR (Claude-style) with subjects as the workspace
switcher. Warm, editorial, content-first — NOT a generic SaaS template. Warm off-white background,
hairline borders, one restrained accent, serif display headings + Inter/Geist body. Components from
shadcn/ui + 21st.dev (+ Origin/Kibo UI); tweakcn for theme tokens. Signature screens: Subject home,
the feedback reading view with EXPANDABLE CITATIONS showing the exact grounding passage, and an
editable Question→Concept→Rubric concept-map (react-flow).

Start with Phase 0 and report the acceptance check result before continuing.
```

---

## 19. Decisions baked in (override any of these)
1. **One Postgres** (pgvector + Apache AGE) for relational + vectors + graph. Lowest latency, one source of truth, cheapest.
2. **Firebase kept only for Auth + Storage** (free, already in your docs).
3. **In-droplet Postgres** for the FYP; managed DO/Azure Postgres is the production upgrade.
4. **Minimal knowledge graph** (3 relationship types); relational-table fallback if AGE is fiddly.
5. **Performance-first models:** `gpt-oss-120b` grader, `qwen3-32b` judge, `gpt-oss-20b` utility. Accuracy comes from the pipeline, not model size — step up the grader only if you want.
6. **Consolidate on DigitalOcean**; Azure $100 is reserve.
7. **Subjects are single-owner**; co-teaching is out of scope.

---

## References (for the report)
- HybridRAG — combining knowledge graphs with vector RAG — arXiv:2408.04948.
- KG²RAG — knowledge-graph-guided RAG (fact-level relationships between chunks improve retrieval and answer quality).
- GraphRAG-vs-vector-RAG guidance — vectors for unstructured semantic retrieval; graphs for multi-hop/relationship reasoning; hybrid for both.
- pgvector (Postgres vector search, HNSW) and Apache AGE (Postgres graph, openCypher) documentation.
- DigitalOcean Gradient — serverless inference, model catalogue & pricing, embeddings/reranking. *(Re-verify model names and prices.)*

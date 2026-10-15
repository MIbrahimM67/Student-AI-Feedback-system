# GradeWise document and code demo (2–3 months)

Use the `deploy/document-demo` branch. This is an invite-only, low-traffic demo,
not a production deployment. Source lives in GitHub, the existing frontend stays
on Vercel, and one backend web service runs on Render Free or Railway. An external
Neon Free Postgres database stores app records, original files and queued jobs.
The platform does not host an AI model: the existing Gradient/Groq/vision calls
still require working credentials and may cost money.

## Scope and limits

- Student text/PDF/DOCX/image submission and instructor **single-document** grading.
- Subject reference indexing, cited text retrieval, internal text similarity, instructor review and PDF reports are available.
- Python, C++17 and Java (`Main` class) single-file coding use real Vercel Sandbox
  microVMs. Batches of up to 30 individual files are available. Multi-file ZIP code projects and internet plagiarism remain paused. Hosted KB retrieval uses full-text search; embeddings remain available for full deployments with a configured provider.
  Execution failures never fall back to simulation.
- One grading/indexing job at a time, 20-minute job timeout, 5 MB/file, 20 PDF pages,
  60,000 extracted characters/document, 100 MB total original-file storage.
- DOCX currently extracts paragraph text, not embedded figures. Use PDF for visual
  documents. Images/scanned PDFs require your configured vision model; without one,
  start with typed PDFs or TXT. Do not assume visual evidence was read without
  checking extraction output and a representative graded example.
- Allowlisted Firebase UIDs only; auth is never mocked. Originals are stored behind
  RLS and authenticated downloads, not exposed via a public static uploads folder.
  A valid Google account outside the invite list receives HTTP 403 with its own
  account ID. Add that exact ID to `DEMO_ALLOWED_UIDS` and redeploy to invite it;
  do not disable token verification or open the demo to all Google accounts.
- Pending work survives restarts. An interrupted running job is marked failed when
  the next consumer starts; upload it again. We do not silently repeat AI charges.
- Optional `DEMO_KEEPALIVE_ENABLED=true` sends a lightweight request to the Render
  external `/ping` endpoint every ten minutes while the process runs. It does not
  query Postgres or call AI. It cannot wake an already stopped process or prevent
  provider restarts/outages/quota exhaustion. Free service hours still apply.
  The worker does not poll the database while idle.

## 1. Create the persistent database

Create a **Neon Free** project in a region near your backend. Use a new, dedicated
database; do not reuse another project's database. No old DigitalOcean records are
recovered by this process. Your old `.env` provides credentials, not a data backup.
Keep any discovered backup untouched; this bootstrap refuses an existing schema.

Install `asyncpg` on your computer, clone this branch, then run:

```bash
python -m pip install asyncpg==0.30.0
python backend/scripts/prepare_demo_db.py
```

The script privately prompts for the database **owner direct URL** and a new,
generated app password. It applies `postgres/init.sql` and `backend/demo_schema.sql`
in one transaction and writes `.env.demo.database` with the restricted `app_user`
URL. This file is ignored by git. Never paste its contents into chat or commit it.
Use a direct endpoint: transaction poolers are incompatible with the worker's
session advisory lock. The app fails startup if its role can bypass RLS.

The bootstrap needs permission to create extensions (`vector`, `pgcrypto`) and a
restricted SQL role. Do not create app_user through Neon's role UI: initialize it
with the script. Do not put owner credentials in backend environment variables.

## 2. Deploy one backend

### Render (recommended for a strictly free demo)

Connect GitHub, allow access to the private GradeWise repo, choose **New Blueprint**,
select this branch and its root `render.yaml`. Confirm the service says **Free**.
There is no Render database, Redis, paid worker, persistent disk or cron service.
Render's free database expires after 30 days, so use the external database above.

The Blueprint asks for:

- `DATABASE_URL`: the restricted direct URL generated above.
- `DEMO_ALLOWED_UIDS`: your Firebase Authentication user UID, optionally comma-separated
  with the UIDs of invited testers (not emails). An empty list fails startup.
- Existing `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`,
  `FIREBASE_PRIVATE_KEY` and `FIREBASE_STORAGE_BUCKET` from your private `.env`.

Add your existing optional inference/vision settings if used:
`DEDICATED_INFERENCE_BASE_URL`, `DEDICATED_INFERENCE_TOKEN`, `DEDICATED_MODEL`,
`DEDICATED_VISION_BASE_URL`, `DEDICATED_VISION_TOKEN`, `DEDICATED_VISION_MODEL`,
`GRADIENT_VISION_OCR_MODEL`. Preserve model IDs from the working configuration.
Do not copy the deleted Droplet's `DATABASE_URL` or `REDIS_URL`.

When dedicated inference is configured, the demo uses it for rubric decomposition,
small and large documents, and utility text calls. `GRADIENT_API_KEY` is then optional.
For a one-time deployment check, set `DEMO_VERIFY_PROVIDERS=true`: startup verifies
the first invited Firebase user and grades a synthetic text document with real AI
calls. If visual extraction is enabled, it also checks the vision API with a
synthetic image. Set it back to `false` after verification succeeds. No user documents or
database records are created by this check.
The Groq deployment uses `openai/gpt-oss-120b`; check model availability for your
account before reusing an older Llama model ID. Embedding-backed knowledge-base
indexing/search and plagiarism checks are paused in demo mode, including for
assignments whose stored settings enabled them before the migration.

The current Render service uses native Python 3.11.11 with build command
`python -m pip install -r backend/requirements.txt`, no root directory, and start
command `cd backend && exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`.
The Docker Blueprint remains an equivalent alternative for creating a new service.

The demo grades directly against the uploaded reference. For more than about
2,000 combined submission/reference tokens, configure the existing high-context
dedicated endpoint (for example the project's Groq integration); otherwise the
job fails explicitly. Start with a short typed document when testing Gradient
alone. Model usage is separate from free web hosting.

Render supplies HTTPS and `PORT`. Expect a cold start after idle periods. Check
`/health` returns 200 and `/api/capabilities` reports the document demo enabled.
API/AI failures must be corrected before switching the existing Vercel deployment.

### Railway (optional, same backend image)

Connect this GitHub branch and set service **Root Directory** to `/backend`.
Use `/backend/railway.json` as the config path if it is not discovered automatically.
It builds `Dockerfile.demo` and uses `$PORT`; generate a public HTTPS domain.
Set all the values from `render.yaml` manually, including `DOCUMENT_DEMO=true`,
`CODE_EXECUTION_ENABLED=false`, `USE_MOCKS=false`, `DEBUG=false`, `DB_POOL_MAX_SIZE=4`,
`FRONTEND_URL`, and the secret/invite values above. Use one replica and one Uvicorn
worker. Use the external database; do not add separately billed Railway data services.

Railway's current trial is $5 for up to 30 days, then the Free plan has $1/month
non-rollover usage credit. Do not assume this covers a continuously running app for
3 months. Limited trials restrict outbound networking, which may block the database
or AI provider. Check trial verification and actual usage before selecting Railway.
Do not upgrade to a paid plan just to pass verification without reviewing its cost.

## 3. Connect Vercel after backend checks pass

Deploy the frontend changes from this branch in a preview first, with:

```text
NEXT_PUBLIC_DOCUMENT_DEMO=true
NEXT_PUBLIC_API_BASE_URL=https://YOUR-BACKEND-HOST
```

If the existing API URL is a legacy write-only Vercel Secret that cannot be
updated as public Config, set `NEXT_PUBLIC_DOCUMENT_DEMO_API_URL` to the demo
backend instead. With demo mode enabled, both authentication and application API
requests use that value; previews can continue using `NEXT_PUBLIC_API_BASE_URL`.
Save the demo flag and URL as public Config for the intended environment, then
redeploy. These values contain no credentials.

Keep the existing `NEXT_PUBLIC_FIREBASE_*` values. Set backend `DEMO_PREVIEW_URL` to
the exact preview origin for testing; keep `FRONTEND_URL` for production. Redeploy
after changing `NEXT_PUBLIC_*`: Next.js embeds these at build time. Only public
frontend settings belong in Vercel; no database password or AI/service-account key.
After verification, deploy the branch/merge to main and set the production backend
URL. No frontend cutover is performed by adding these files to GitHub.

## Acceptance check before sharing

1. Invited Google sign-in succeeds; a non-invited Firebase account is rejected.
2. Submit one short typed PDF and a reference; check a real feedback report and PDF
   download. Inspect the score/explanation, not just an HTTP success.
3. Instructor single upload completes and can be reviewed/approved.
4. Python/C++/Java stdout, compilation failures and timeout errors come from actual
   execution. ZIP submissions remain unavailable. No simulated grades appear.
5. Restart the service: saved documents/reports remain; pending jobs run again on
   startup; interrupted work shows failure rather than staying processing forever.
6. Check actual memory and provider consumption with representative documents.
   The 512 MB free service still needs a real workload test; no capacity guarantee.

## Data retention

Take a `pg_dump` using the private owner URL before/after important demos and keep
the backup away from the hosting service. `demo_files` are in the dump. Free tiers
are not backups. To clear old originals intentionally, the database owner can delete
selected rows from `demo_files`; its trigger updates the storage counter. Deleting
a submission currently does not automatically delete its stored original.

Provider docs checked 2026-10-03:
- https://render.com/docs/free
- https://neon.com/pricing
- https://docs.railway.com/pricing/free-trial

## Real code execution setup

Deploy the frontend bridge before enabling backend coding. It uses Vercel's automatic
OIDC credentials; no database or AI secrets belong in the frontend. The committed
RSA public key verifies 60-second body-bound requests signed by the existing backend
Firebase service-account private key, under an execution-specific signature namespace.
A service-account key rotation requires updating `executor-public-key.ts` as well.

Set backend `CODE_RUNNER_URL` to the production Vercel origin plus
`/api/internal/code-execution`. Leave `CODE_EXECUTION_ENABLED=false` until a deployment
with `DEMO_VERIFY_CODE_RUNNER=true` passes actual Python, C++ and Java stdin/output,
CPU/wall timeout and network-isolation checks. Then set `CODE_EXECUTION_ENABLED=true`
and `DEMO_VERIFY_CODE_RUNNER=false`. UI capability checks reveal coding only when the
backend enables it. This verifier uses synthetic programs, not user submissions.

The runner caches a compiler-only snapshot, compiles once per submission, runs up to
five stdin cases in a disposable VM, and always stops it. Submitted programs run as
an unprivileged user, without outbound network or host credentials. Per-case time
limit is five seconds; compilation limit is fifteen seconds. Python/C++ address
space and Java heap are bounded; stdout/stderr are truncated. No uploaded program is
executed in the Vercel function or Render process. The Specialist, Judge and Senior
stages/models are preserved and receive actual execution evidence with the code.
Exit code zero means the program ran; the rubric determines correctness.

Vercel Hobby Sandbox includes limited CPU/memory hours, creations and snapshot storage;
when its free allowance is exhausted, execution is unavailable. Warm snapshots avoid
reinstalling compilers each run, but first setup and serverless cold starts can take
longer. Free hosting does not guarantee zero latency or continuous uptime. Check quotas
before the presentation and run one representative document and coding example.

Provider docs checked 2026-10-05:
- https://vercel.com/docs/vercel-sandbox/pricing
- https://vercel.com/docs/vercel-sandbox
- https://render.com/docs/free



## Core instructor features (October 2026)

Apply `backend/core_features_schema.sql` as the database owner before deploying this version. It preserves existing vectors, permits text-only chunks and adds a full-text index. Instructors can upload a ZIP of 1–30 individual submissions (100 MB archive/expanded total; each file 5 MB and at most 20 PDF pages), review names and start durable sequential jobs. Mixed unsupported files, encrypted archives and unsafe paths are rejected before storage. Multi-file code projects are still outside this deployment.

Reference uploads are available to every approved instructor. Batch ZIP upload, internal similarity and exports (Excel, ZIP of PDFs and single-report PDFs) need an active Pro plan; the backend enforces this, and instructor tools as a whole require an administrator-approved faculty application. On this deployment an approved instructor activates Pro from the subscription dialog (sandbox upgrade or voucher); no card is charged. Hosted knowledge-base retrieval uses subject-scoped full-text search with passage IDs and source titles; it does not pretend these are semantic embeddings. The existing embedding/reranking path is retained for full deployments with a valid provider. Internal similarity measures TF-IDF and word-trigram overlap within a batch, or the 30 most recent graded submissions to the same assignment for single uploads. Scores and source matches refresh for earlier submissions too; they are review signals and never change rubric marks.

Existing assignments saved by the old demo may have these options switched off. Enable Internal similarity and Use subject knowledge base in their settings. New assignments default to both enabled for Pro instructors; for other instructors similarity is saved as off. Similarity is also skipped at grading time if the assignment owner no longer has Pro. Model stages and remote code execution remain unchanged. Internet plagiarism, multi-file projects and institution/billing integrations remain unavailable.

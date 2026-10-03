# GradeWise: temporary AWS hosting (2–3 months)

Status: deployment preparation, not a live migration. Source inspected at upstream
commit `72d82d2508e33605f9f5a789e68e8c2e8fc3bcc8`. AWS account access, actual
credit eligibility, secrets, domain, and old data availability remain unverified.

## Hosting choice and cost

Use one dedicated Ubuntu 24.04 x86-64 VM with 2 vCPU / 4 GB RAM to start. Run
FastAPI, one Celery worker, Celery Beat, PostgreSQL 16/pgvector, Redis, and Caddy
on that VM. Keep the existing Vercel frontend and Firebase project. No GPU is
needed because inference runs through external APIs. Capacity is provisional:
verify a representative PDF and batch job before deciding to use less RAM.

AWS Lightsail's public-IPv4 4 GB Linux bundle is listed at $24/month as checked
2026-10-03: $48–$72 base compute for 2–3 months. Backups, transfer overages,
taxes, domains, Firebase and external AI usage are additional. Do not assume
AWS credits cover Lightsail or external AI. Verify eligible services and expiry
in the actual account before creating the instance. If the account's credit plan
only supports EC2, use the same Docker deployment on EC2 after pricing compute,
EBS and public IPv4 in the chosen region; this document does not quote an EC2 total.

Sources:
- https://aws.amazon.com/lightsail/pricing/
- https://aws.amazon.com/free/

## Required before launch

1. AWS account access and confirmed credits, expiration and eligible services.
2. A DNS hostname for the API and access to its DNS settings.
3. The old backend environment secrets, including Firebase private key and
   DigitalOcean Gradient API key. Never paste these into GitHub or public logs.
4. A database dump/snapshot and `/app/uploads` volume backup if old data matters.
   The repo contains the schema, not old student records. Firebase sign-in users
   are separate from PostgreSQL user profiles/roles and will not recreate them.
5. Confirm DigitalOcean inference still works. The code directly uses its BGE-M3
   embeddings (existing vector schema) and reranker plus chat. A deleted Droplet
   does not itself require replacing those APIs; deleted/inactive AI services do.
   Replacing them with Bedrock is a separate provider/schema migration, not an
   environment-variable switch. AWS hosting credit does not pay DigitalOcean/Groq.

## Prepare the VM

- Verify the selected region's price and account plan, then provision the VM.
- Attach a static IPv4 for Lightsail. Set the API hostname's A record to it.
- Allow inbound TCP 80/443. Restrict SSH 22 to the operator's IP. Never expose
  PostgreSQL 5432, Redis 6379 or API 8000. Only Caddy is public.
- Install Docker Engine and Compose v2 from Docker's official Ubuntu guide:
  https://docs.docker.com/engine/install/ubuntu/
- Check out this branch of the private repo using an authorized GitHub session.
  Use a dedicated VM: the inherited code runner has Docker socket access and can
  control that host. Do not place other projects or AWS administrative keys on it.
- Copy `deploy/aws/.env.example` to `.env.aws` in the repo root and fill values.
  Generate each database password separately with `openssl rand -hex 32`.
- Preserve any optional inference, OCR, plagiarism and Stripe settings in use.

## Fresh start

Only use a fresh database after deciding old data is unnecessary or unavailable.

```bash
python3 deploy/aws/check_env.py .env.aws
bash deploy/aws/start.sh
```

The standalone `compose.production.yaml` replaces, rather than extends, the
development compose configuration. There are no source bind mounts or Uvicorn
reload. The start script validates settings, generates a restricted runtime env
file, initializes/checks the app database role, pulls code-runner images, starts
the services, and checks the API and Celery response. Caddy obtains HTTPS after
DNS resolves and ports 80/443 are reachable. Do not print resolved Compose config:
it contains secrets; use `config --quiet`.

## Restore existing data

Do this before starting API/worker/beat (the scheduler can purge expired records).
Restore first into a separate empty database/VM; never overwrite the only backup.
For a PostgreSQL custom-format dump:

```bash
bash deploy/aws/start.sh --prepare-only
docker compose --env-file .env.aws -f compose.production.yaml up -d --wait postgres redis
docker compose --env-file .env.aws -f compose.production.yaml exec -T postgres \
  createdb -U feedback -T template0 restore_check
docker compose --env-file .env.aws -f compose.production.yaml exec -T postgres \
  pg_restore -U feedback -d restore_check --no-owner --no-privileges --exit-on-error < /secure/path/old.dump
```

Inspect the restored schema, table counts, owners, RLS policies, vector dimensions
and file references before choosing it as production. This command is a rehearsal,
not a cutover: plan the production database switch after inspecting the actual dump
format and schema version. Plain SQL dumps and Droplet snapshots require different
restore steps. Reapply the app role/password and grants as owner; restored
`--no-privileges` data requires the application's table/sequence grants before use.
Copy the matching uploads archive into the production `api_uploads` volume.
Do not use `docker compose down -v`; it deletes named volumes and their data.

## Verification and frontend cutover

1. Public `https://API_DOMAIN/health` returns 200 and both dependencies `ok`.
2. `POST /_debug/embed` returns 404 in production (no unauthenticated AI spend).
3. A real Firebase login works; invalid/missing tokens cannot access private APIs.
4. Upload a reference; verify indexing, then grade a representative PDF and a
   coding submission. Verify results, downloads, and a small batch. `/health`
   alone does not prove Firebase, AI APIs, image pulls, or grading are working.
5. Verify code tests really ran. The inherited code runner can fall back to
   simulated results if Docker fails; treat that as a launch blocker for coding
   assessment. The shared host/worker sandbox path fixes the mount mismatch, but
   the runner still needs live validation and a separate security review for
   untrusted public use. The old app also serves uploaded files by static URL;
   this migration does not add per-file access control.
6. In Vercel, set production `NEXT_PUBLIC_API_BASE_URL=https://API_DOMAIN` and
   redeploy; it is a build-time value. Test login/upload/grading from the Vercel
   site before considering the migration complete. Keep FRONTEND_URL set to that
   production frontend for Stripe redirects. Update the Stripe webhook endpoint
   only if billing is active, preserving its correct signing secret.

## Backups, operation, and end of project

Run `bash deploy/aws/backup.sh /secure/backups` during a maintenance window; it
pauses writes, exports PostgreSQL and uploads, then restarts services even on
failure. Copy both outputs to secure storage outside the VM and verify a restore.
Keep the environment secrets separately backed up. Configure scheduled off-VM
backups/snapshots after account access is available; none are scheduled by these files.

Check disk usage and service logs during the first real batch. Container logs rotate;
PostgreSQL/uploads still grow. Set cost alerts in AWS, understanding alerts are not
spending caps. At the end of 2–3 months, export/verify the final backup before
deleting the server, unused IPs, and other billable resources. Merely stopping a
server may leave storage and other charges. Nothing here schedules deletion.

## Validation performed before deployment

The preparation environment has no Docker or AWS credentials. Only Python syntax,
shell syntax, YAML structure and environment preflight regression checks can run
there. A full container build, actual PostgreSQL initialization, provider calls,
public HTTPS, restore and end-to-end grading must be verified on the target VM.

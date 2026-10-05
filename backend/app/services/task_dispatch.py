"""Celery on full deployments; one durable, embedded consumer on the demo.

Use a DIRECT Postgres endpoint: the consumer holds a session advisory lock while
grading to prevent overlap during rolling deploys. No idle polling or keepalives.
Interrupted jobs fail visibly, rather than silently repeating billable AI calls.
"""
import asyncio
from contextlib import suppress
import logging

from app.config import settings
from app.db.postgres import get_conn, get_pool

logger = logging.getLogger(__name__)
LOCK_ID = 7182649301
_wake = asyncio.Event()
_worker = None


async def dispatch(task: str, args: list, *, conn=None) -> None:
    if not settings.DOCUMENT_DEMO:
        if conn is not None:
            return  # Full deployments dispatch after the caller commits.
        from app.workers.celery_app import celery_app
        celery_app.send_task(task, args=args)
        return
    if task not in {"tasks.grade_submission", "tasks.index_reference_material"}:
        raise ValueError("Batch grading is paused in the document demo")
    if conn is None:
        async with get_conn(str(args[1])) as transaction:
            await dispatch(task, args, conn=transaction)
        _wake.set()
        return
    await conn.execute(
        """INSERT INTO demo_jobs(task, target_id, org_id, subject_id)
           VALUES ($1,$2,$3,$4) ON CONFLICT(task,target_id) DO NOTHING""",
        task, args[0], args[1], args[2] if len(args) > 2 else None,
    )
    # Callers using a transaction call notify() after committing it.


def notify() -> None:
    _wake.set()


async def _fail(job, message: str) -> None:
    async with get_conn(str(job["org_id"])) as conn:
        if job["task"] == "tasks.grade_submission":
            # Do not downgrade an already committed report after a shutdown.
            await conn.execute(
                """UPDATE submissions SET status='failed', progress_stage='failed',
                   progress_message=$2, progress_updated_at=now()
                   WHERE id=$1 AND status IN ('uploaded','processing')""",
                job["target_id"], message,
            )
        else:
            await conn.execute(
                "UPDATE reference_materials SET index_status='failed' WHERE id=$1 AND index_status != 'embedded'",
                job["target_id"],
            )
        await conn.execute("UPDATE demo_jobs SET status='failed', finished_at=now() WHERE id=$1", job["id"])


async def _execute(job) -> None:
    if job["task"] == "tasks.grade_submission":
        from app.services.grading_task import run_grade_submission
        await run_grade_submission(str(job["target_id"]), str(job["org_id"]))
    else:
        from app.services.indexing_service import run_indexing
        await run_indexing(str(job["target_id"]), str(job["org_id"]), str(job["subject_id"]))


async def _drain() -> bool:
    async with get_pool().acquire() as lock_conn:
        if not await lock_conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_ID):
            return False  # The previous deployment is still finishing a job.
        try:
            # Holding the lock proves no other demo consumer is executing these.
            interrupted = await lock_conn.fetch("SELECT * FROM demo_jobs WHERE status='running'")
            for job in interrupted:
                await _fail(job, "Server restarted during grading. Please upload the document again.")
            while True:
                job = await lock_conn.fetchrow(
                    """UPDATE demo_jobs SET status='running' WHERE id=(
                         SELECT id FROM demo_jobs WHERE status='pending' ORDER BY id LIMIT 1
                       ) RETURNING *"""
                )
                if job is None:
                    return True
                # Cancel the grading coroutine if the lock connection is lost.
                # Otherwise a reconnect/rolling deployment could grade it twice.
                execution = asyncio.create_task(_execute(job))
                def connection_lost(_):
                    execution.cancel()
                lock_conn.add_termination_listener(connection_lost)
                try:
                    await asyncio.wait_for(execution, timeout=1200)
                    await lock_conn.execute(
                        "UPDATE demo_jobs SET status='done', finished_at=now() WHERE id=$1", job["id"]
                    )
                except asyncio.CancelledError:
                    # Leave running state for recovery after the lock is released.
                    raise
                except Exception:
                    logger.exception("Demo job %s failed", job["id"])
                    await _fail(job, "Grading failed. Check the AI configuration and upload again.")
                finally:
                    with suppress(Exception):
                        lock_conn.remove_termination_listener(connection_lost)
        finally:
            with suppress(Exception):
                await lock_conn.execute("SELECT pg_advisory_unlock($1)", LOCK_ID)


async def _consume() -> None:
    while True:
        await _wake.wait()
        _wake.clear()
        try:
            drained = await _drain()
            if not drained:
                await asyncio.sleep(5)
                _wake.set()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Demo queue temporarily unavailable")
            await asyncio.sleep(10)
            _wake.set()


def start_worker() -> None:
    global _worker
    if not settings.DOCUMENT_DEMO:
        return
    _wake.set()  # Drain durable pending jobs after a cold start.
    _worker = asyncio.create_task(_consume(), name="document-demo-worker")


def worker_healthy() -> bool:
    return not settings.DOCUMENT_DEMO or (_worker is not None and not _worker.done())


async def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.cancel()
        with suppress(asyncio.CancelledError):
            await _worker
        _worker = None

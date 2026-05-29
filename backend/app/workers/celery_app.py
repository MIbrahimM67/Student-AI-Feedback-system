"""
GradeWise v3 — Celery app and task definitions.

Workers handle:
  - index_reference_material: chunk → embed → concept extract → insert reference_chunks
  - grade_submission:         run the full 10-step pipeline for one submission
  - run_batch_grading:        orchestrate grade_submission across all files in a batch
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from celery import Celery

logger = logging.getLogger(__name__)

celery_app = Celery(
    "gradewise",
    broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,          # don't ack until done (safer on crashes)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, # one task at a time per worker (grading is heavy)
)

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "purge-expired-subjects-daily": {
        "task": "tasks.purge_expired_subjects",
        "schedule": crontab(hour=0, minute=0),  # Run daily at midnight UTC
    },
}


def _run_async(coro):
    """Run an async coroutine from a sync Celery task.
    
    Creates a fresh event loop + asyncpg pool for every invocation.
    Celery prefork workers spawn a new event loop on each task attempt,
    so reusing a pool from a previous loop causes 'Future attached to a
    different loop' errors.
    """
    from app.db.postgres import init_pool, close_pool

    loop = asyncio.new_event_loop()
    try:
        # Always create a fresh pool bound to this event loop
        try:
            loop.run_until_complete(close_pool())
        except Exception:
            pass
        loop.run_until_complete(init_pool())
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(close_pool())
        except Exception:
            pass
        loop.close()


@celery_app.task(name="tasks.index_reference_material", bind=True, max_retries=3)
def index_reference_material(self, reference_id: str, org_id: str, subject_id: str):
    """
    Background job: download reference file → chunk → embed → concept extract → insert.
    Called when an instructor uploads a reference to a subject.
    """
    from app.services.indexing_service import run_indexing

    try:
        _run_async(run_indexing(
            reference_id=reference_id,
            org_id=org_id,
            subject_id=subject_id,
        ))
    except Exception as exc:
        logger.error("Indexing failed for reference=%s: %s", reference_id, exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.grade_submission", bind=True, max_retries=2)
def grade_submission(self, submission_id: str, org_id: str):
    """
    Run the full 10-step pipeline for one submission.
    Called by both single-submit and batch routes.
    """
    from app.services.grading_task import run_grade_submission

    try:
        _run_async(run_grade_submission(submission_id=submission_id, org_id=org_id))
    except Exception as exc:
        logger.error("Grading failed for submission=%s: %s", submission_id, exc)
        raise self.retry(exc=exc, countdown=15)


@celery_app.task(name="tasks.run_batch_grading", bind=True, max_retries=1)
def run_batch_grading(self, batch_id: str, org_id: str):
    """
    Dispatch grade_submission for every submission in the batch.
    Submissions are graded concurrently (Celery group).
    """
    from celery import group
    from app.services.grading_task import get_batch_submission_ids

    submission_ids = _run_async(
        get_batch_submission_ids(batch_id=batch_id, org_id=org_id)
    )

    job = group(
        grade_submission.s(sid, org_id)
        for sid in submission_ids
    )
    job.apply_async()


@celery_app.task(name="tasks.purge_expired_subjects", bind=True)
def purge_expired_subjects(self):
    """
    Background job: run daily via Celery Beat.
    Deletes any subjects where now() > expires_at + 14 days grace period.
    """
    async def _purge():
        from app.db.postgres import get_conn
        async with get_conn() as conn:
            # Delete subjects where expires_at was more than 14 days ago.
            # CASCADE will automatically delete assignments, submissions, chunks, etc.
            result = await conn.execute(
                "DELETE FROM subjects WHERE now() > expires_at + interval '14 days';"
            )
            logger.info("Purged expired subjects: %s", result)
    
    _run_async(_purge())
    logger.info("Dispatched %d grading tasks for batch=%s", len(submission_ids), batch_id)

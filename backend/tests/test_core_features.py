"""Core features: bounded archives, real Postgres storage/retrieval and queue behavior.

Optional isolated branch integration uses GW_BRANCH_DATABASE_URL. Never resets data.
AI grading responses are controlled test doubles; database operations are real.
"""
import io
import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid
import zipfile

os.environ.setdefault('DOCUMENT_DEMO','true')
os.environ.setdefault('DB_POOL_MAX_SIZE','4')
import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from app.services.batch_ingestion import archive_members, stage_archive
from app.services.internal_similarity import compare_texts


def zip_upload(count=3, names=None, contents=None):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
        for i in range(count):
            z.writestr(names[i] if names else f'student_{i}.txt',contents[i] if contents else 'Ice floats because it is less dense than liquid water.')
    data.seek(0)
    return UploadFile(data,filename='class.zip')


@pytest.mark.asyncio
async def test_accepts_exactly_30_files_and_rejects_31():
    async with stage_archive(zip_upload(30),'text') as entries:
        assert len(entries)==30
        assert all(e['path'].is_file() for e in entries)
        paths=[e['path'] for e in entries]
    assert all(not path.exists() for path in paths)
    with pytest.raises(HTTPException) as exc:
        async with stage_archive(zip_upload(31),'text'):
            pass
    assert exc.value.status_code==400


@pytest.mark.asyncio
@pytest.mark.parametrize('filename',['../escape.txt','/root.txt','C:\\escape.txt','student/program.zip'])
async def test_unsafe_and_nested_project_files_rejected(filename):
    with pytest.raises(HTTPException):
        async with stage_archive(zip_upload(1,[filename]),'text'):
            pass


@pytest.mark.asyncio
async def test_compressed_oversized_file_rejected_before_expansion():
    from app.config import settings
    with pytest.raises(HTTPException) as exc:
        async with stage_archive(zip_upload(1,contents=['x'*(settings.DEMO_MAX_FILE_MB*1024*1024+1)]),'text'):
            pass
    assert exc.value.status_code==413


def test_similarity_is_symmetric_and_detects_identical_text():
    texts=['Water freezes at zero degrees Celsius. Ice has lower density than water.',
           'Water freezes at zero degrees Celsius. Ice has lower density than water.',
           'Sorting algorithms arrange numerical sequences according to specified ordering rules.']
    m=compare_texts(texts)
    assert m[0][1]==m[1][0]==100
    assert m[0][2]<15
    assert compare_texts(['','Nothing here'])[0][1]==0


from test_document_demo import db

@pytest_asyncio.fixture
async def branch_db(db, monkeypatch):
    from app.db import postgres
    from app.api.instructor_routes import create_assignment, CreateAssignmentRequest
    owner, org = db
    uid='tester'
    async with postgres.get_conn(str(org)) as conn:
        await conn.execute("UPDATE users SET role='instructor',faculty_status='approved' WHERE uid=$1",uid)
        subject=str(await conn.fetchval("INSERT INTO subjects(org_id,instructor_id,title) VALUES($1,$2,'Synthetic science') RETURNING id",org,uid))
    result=await create_assignment(subject,CreateAssignmentRequest(title='Water',prompt='Explain the density of ice',rubric='Accuracy: 10 marks',total_marks=10),{'org_id':org,'uid':uid})
    assignment=str(result['id'])
    yield {'org':str(org),'uid':uid,'subject':subject,'assignment':assignment}


@pytest.mark.asyncio
async def test_branch_batch_30_storage_queue_and_reciprocal_similarity(branch_db,monkeypatch):
    import httpx
    from app.main import app
    from app.api.instructor_routes import _get_instructor
    from app.db.postgres import get_conn
    from app.services import grading_task, task_dispatch
    from app.grading.types import GradingResult, Tier
    d=branch_db
    app.dependency_overrides[_get_instructor]=lambda:{'uid':d['uid'],'org_id':d['org'],'role':'instructor','faculty_status':'approved'}
    monkeypatch.setattr(grading_task.warning_service,'scan_and_enforce',AsyncMock(return_value=(False,None)))
    async def grader(**kwargs):
        return GradingResult(score=8,max_score=10,per_criterion={'accuracy':8},feedback='Controlled test feedback',tier_used=Tier.CONTEXT,reference_sections_used=[])
    monkeypatch.setattr(grading_task,'route_and_grade',grader)
    # Empty KB uses no provider calls; controlled grader avoids billable inference.
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            original=zip_upload(30)
            response=await client.post('/api/instructor/batch',data={'assignment_id':d['assignment'],'subject_id':d['subject']},files={'file':('class.zip',original.file.read(),'application/zip')})
            assert response.status_code==202,response.text
            batch=response.json()['batch_id']; assert response.json()['total_files']==30
            for _ in range(2):
                start=await client.post(f'/api/instructor/batch/{batch}/process');assert start.status_code==200,start.text
            async with get_conn(d['org']) as conn:
                assert await conn.fetchval("SELECT count(*) FROM demo_jobs WHERE org_id=$1 AND task='tasks.grade_submission'",d['org'])==30
                jobs=await conn.fetch('SELECT * FROM demo_jobs WHERE org_id=$1 ORDER BY id',d['org'])
            # Execute all jobs through the real dispatch path, one at a time.
            for job in jobs:
                await task_dispatch._execute(job)
            async with get_conn(d['org']) as conn:
                assert await conn.fetchval('SELECT count(*) FROM feedback_reports WHERE batch_id=$1',batch)==30
                scores=await conn.fetch('SELECT similarity_score FROM plagiarism_reports WHERE batch_id=$1',batch)
                assert len(scores)==30 and all(float(r['similarity_score'])==100 for r in scores)
                assert await conn.fetchval('SELECT status FROM batches WHERE id=$1',batch)=='completed'
                assert await conn.fetchval('SELECT count(*) FROM submissions WHERE batch_id=$1 AND status=\'graded\'',batch)==30
            reports=await client.get(f'/api/instructor/batch/{batch}/reports');assert len(reports.json()['reports'])==30
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_branch_reference_index_and_cited_retrieval(branch_db,monkeypatch):
    from app.api.instructor_routes import upload_reference
    from app.services import indexing_service
    from app.services.retrieval_service import retrieve_text_chunks
    from app.db.postgres import get_conn
    d=branch_db
    llm=SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(text='{"concepts":[]}')))
    monkeypatch.setattr(indexing_service,'build_llm_from_env',lambda:llm)
    upload=UploadFile(io.BytesIO(b'Ice floats because ice has lower density than liquid water. Water freezes at zero degrees Celsius.'),filename='notes.txt')
    result=await upload_reference(d['subject'],'Ice and density','lecture_notes',upload,{'uid':d['uid'],'org_id':d['org']})
    await indexing_service.run_indexing(result['reference_id'],d['org'],d['subject'])
    chunks=await retrieve_text_chunks(d['org'],d['subject'],'ice density')
    assert chunks and 'lower density' in chunks[0]['text']
    assert chunks[0]['id'] and chunks[0]['title']=='Ice and density'
    async with get_conn(d['org']) as conn:
        ref=await conn.fetchrow('SELECT index_status,index_method,chunk_count FROM reference_materials WHERE id=$1',result['reference_id'])
    assert dict(ref)=={'index_status':'embedded','index_method':'full_text','chunk_count':1}
    assert not await retrieve_text_chunks(str(uuid.uuid4()),d['subject'],'ice density')
    from app.services.grading_task import _retrieve_subject_kb_context
    context=await _retrieve_subject_kb_context(llm=llm,org_id=d['org'],subject_id=d['subject'],assignment_prompt='Explain the density of ice',raw_rubric='Accuracy',submission_text='Ice floats',course_weight=60,ai_weight=40)
    assert 'Ice and density' in context and 'lower density' in context
    assert chunks[0]['id'] in context

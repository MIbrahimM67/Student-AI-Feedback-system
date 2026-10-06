"""Local files on a VM; bounded, tenant-scoped Postgres blobs in the demo."""
from contextlib import asynccontextmanager
from pathlib import Path
import os
import tempfile
from urllib.parse import quote
import uuid

from fastapi import HTTPException
from app.config import settings
from app.db.postgres import get_conn
from app.services import local_storage
from app.services.demo_limits import validate_document

PREFIX = "/api/files/"


async def save_file(content: bytes, blob_name: str, *, org_id, owner_uid: str, kind: str = "text") -> str:
    if not settings.DOCUMENT_DEMO:
        return local_storage.save_file(content, blob_name)
    filename = Path(blob_name).name
    validate_document(content, filename, kind=kind)
    file_id = uuid.uuid4()
    async with get_conn(str(org_id)) as conn:
        # Global budget row serializes concurrent uploads; files themselves enforce RLS.
        used = await conn.fetchval("SELECT bytes_used FROM demo_storage_budget WHERE id = 1 FOR UPDATE")
        if used is None:
            raise RuntimeError("Demo storage schema is missing")
        if used + len(content) > settings.DEMO_STORAGE_MB * 1024 * 1024:
            raise HTTPException(507, "Demo document storage is full. Ask the owner to clear old demo files.")
        await conn.execute(
            "INSERT INTO demo_files (id, org_id, owner_uid, filename, content) VALUES ($1,$2,$3,$4,$5)",
            file_id, org_id, owner_uid, filename, content,
        )
        await conn.execute("UPDATE demo_storage_budget SET bytes_used = bytes_used + $1 WHERE id = 1", len(content))
    return f"{PREFIX}{file_id}/{quote(filename, safe='')}"


@asynccontextmanager
async def materialize(file_url: str, filename: str, org_id):
    """Yield a local path; always remove downloaded/decrypted temporary files."""
    local_path = local_storage.get_local_path(file_url)
    if local_path:
        if not os.path.isfile(local_path):
            raise FileNotFoundError("Uploaded document is missing")
        yield local_path
        return
    if file_url.startswith(PREFIX):
        file_id = uuid.UUID(file_url[len(PREFIX):].split("/", 1)[0])
        async with get_conn(str(org_id)) as conn:
            content = await conn.fetchval("SELECT content FROM demo_files WHERE id = $1", file_id)
        if content is None:
            raise FileNotFoundError("Document not found in this organization")
    else:
        if settings.DOCUMENT_DEMO:
            raise ValueError("Demo documents must be stored in its database")
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(file_url)
            response.raise_for_status()
            content = response.content
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as temp:
        temp.write(content)
        path = temp.name
    try:
        yield path
    finally:
        Path(path).unlink(missing_ok=True)

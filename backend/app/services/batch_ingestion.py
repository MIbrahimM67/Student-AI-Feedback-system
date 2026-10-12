"""Bounded ZIP staging. Never extract archive paths onto the filesystem."""
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

from fastapi import HTTPException
from app.config import settings
from app.services.demo_limits import validate_document


def batch_file_limit() -> int:
    return min(30, max(1, settings.INSTRUCTOR_BATCH_MAX_FILES))


def archive_members(archive: zipfile.ZipFile, kind: str) -> list[zipfile.ZipInfo]:
    entries = []
    paths = set()
    allowed = {'.py', '.cpp', '.cc', '.cxx', '.java', '.txt'} if kind == 'coding' else {'.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg'}
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if path.is_absolute() or '..' in path.parts or '\\' in member.filename or ':' in member.filename or stat.S_ISLNK(member.external_attr >> 16):
            raise HTTPException(422, 'ZIP contains an unsafe path or symbolic link.')
        if member.is_dir() or any(part.startswith('.') or part == '__MACOSX' for part in path.parts):
            continue
        if member.filename in paths:
            raise HTTPException(422, 'ZIP contains duplicate file paths.')
        paths.add(member.filename)
        if path.suffix.lower() not in allowed or member.flag_bits & 1:
            raise HTTPException(415, f'Unsupported or encrypted batch file: {path.name}. Use individual documents or single source files.')
        if member.file_size > settings.DEMO_MAX_FILE_MB * 1024 * 1024:
            raise HTTPException(413, f'Each batch file must be at most {settings.DEMO_MAX_FILE_MB} MB.')
        entries.append(member)
    if not 1 <= len(entries) <= batch_file_limit():
        raise HTTPException(400, f'Upload between 1 and {batch_file_limit()} files per batch.')
    if sum(m.file_size for m in entries) > settings.INSTRUCTOR_BATCH_MAX_MB * 1024 * 1024:
        raise HTTPException(413, 'Expanded batch exceeds the batch size limit.')
    return entries


@asynccontextmanager
async def stage_archive(upload, kind: str):
    if not (upload.filename or '').lower().endswith('.zip'):
        raise HTTPException(415, 'Batch upload must be a ZIP containing individual submission files.')
    with tempfile.TemporaryDirectory(prefix='gradewise-batch-') as directory:
        archive_path = Path(directory) / 'batch.zip'
        size = 0
        with archive_path.open('wb') as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.INSTRUCTOR_BATCH_MAX_MB * 1024 * 1024:
                    raise HTTPException(413, f'ZIP must be at most {settings.INSTRUCTOR_BATCH_MAX_MB} MB.')
                output.write(chunk)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                members = archive_members(archive, kind)
                staged = []
                for index, member in enumerate(members):
                    content = archive.read(member)
                    filename = PurePosixPath(member.filename).name
                    validate_document(content, filename, kind=kind)
                    target = Path(directory) / f'{index}{Path(filename).suffix}'
                    target.write_bytes(content)
                    staged.append({'path': target, 'filename': filename, 'archive_name': member.filename})
                yield staged
        except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
            raise HTTPException(422, 'ZIP is invalid, encrypted or damaged.') from exc

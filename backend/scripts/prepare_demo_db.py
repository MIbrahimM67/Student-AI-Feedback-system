"""Initialize a NEW dedicated demo database. Never run against an existing app DB.

Run from your private terminal: python backend/scripts/prepare_demo_db.py
Requires asyncpg. Credentials are prompted without echo and never printed.
"""
import asyncio
import getpass
import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode

import asyncpg


async def main():
    owner_url = getpass.getpass("Fresh database owner connection URL (direct, not pooled): ").strip()
    parts = urlsplit(owner_url)
    if parts.scheme not in {"postgres", "postgresql"} or not parts.hostname:
        raise ValueError("Expected a postgres:// or postgresql:// connection URL")
    if "-pooler." in parts.hostname:
        raise ValueError("Disable connection pooling in Neon and copy the direct URL")
    # asyncpg does not implement libpq's channel_binding parameter.
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query) if key != "channel_binding"])
    owner_url = urlunsplit(parts._replace(query=query))
    password = getpass.getpass("New app_user password (at least 24 characters): ")
    if len(password) < 24:
        raise ValueError("Use a generated password of at least 24 characters")
    target = Path(".env.demo.database")
    if target.exists():
        raise RuntimeError(".env.demo.database already exists; move it securely before initializing a new database")
    root = Path(__file__).resolve().parents[1]
    connection = await asyncpg.connect(owner_url)
    try:
        if await connection.fetchval("SELECT to_regclass('public.organizations')"):
            raise RuntimeError("Database already contains GradeWise tables; refusing to initialize it")
        async with connection.transaction():
            await connection.execute((root.parent / "postgres/init.sql").read_text())
            # PostgreSQL utility statements cannot bind passwords as parameters.
            # quote_literal runs in the database and safely quotes the supplied secret.
            literal = await connection.fetchval("SELECT quote_literal($1::text)", password)
            await connection.execute(f"ALTER ROLE app_user PASSWORD {literal}")
            await connection.execute((root / "demo_schema.sql").read_text())
    finally:
        await connection.close()
    host_port = parts.netloc.rsplit("@", 1)[-1]
    runtime_url = urlunsplit(parts._replace(netloc=f"app_user:{quote(password, safe='')}@{host_port}", query=query))
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(f"DATABASE_URL={runtime_url}\n")
    print("Schema initialized. Runtime connection saved privately in .env.demo.database.")
    print("Use its DATABASE_URL in Render/Railway. Never deploy the database owner URL.")


if __name__ == "__main__":
    asyncio.run(main())

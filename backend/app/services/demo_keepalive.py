"""Opt-in, low-frequency liveness ping. Does not query Postgres or call AI."""
import asyncio
from contextlib import suppress
import logging
import os
from urllib.parse import urlparse
import httpx

logger = logging.getLogger("uvicorn.error")


async def keepalive() -> None:
    url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".onrender.com"):
        logger.warning("Keep-alive inactive: no Render external URL")
        return
    await asyncio.sleep(30)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        while True:
            try:
                response = await client.get(url + "/ping")
                logger.info("Demo liveness ping: HTTP %s", response.status_code)
            except httpx.HTTPError:
                logger.warning("Demo liveness ping failed; retrying at the next interval")
            await asyncio.sleep(600)


async def stop_keepalive(task) -> None:
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

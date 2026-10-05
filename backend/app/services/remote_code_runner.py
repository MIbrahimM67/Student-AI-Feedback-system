"""Signed requests to isolated execution; no mock or simulated fallback."""
import base64
import hashlib
import json
import time
import uuid
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from app.config import settings


async def execute_tests(code: str, language: str, inputs: list[str]) -> list[dict]:
    url = settings.CODE_RUNNER_URL
    if urlparse(url).scheme != "https" or not urlparse(url).hostname:
        raise RuntimeError("Configure an HTTPS CODE_RUNNER_URL before enabling execution.")
    lang = "cpp" if language.lower() == "c++" else language.lower()
    if lang not in {"python", "cpp", "java"} or not 1 <= len(inputs) <= 5:
        raise RuntimeError("Use Python, C++ or Java with 1–5 code checks.")
    if len(code) > settings.DEMO_MAX_TEXT_CHARS or any(len(i) > 8000 for i in inputs):
        raise RuntimeError("Code or stdin exceeds the demo execution limit.")
    body = json.dumps({"id": str(uuid.uuid4()), "language": lang, "code": code,
                       "inputs": inputs}, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    message = f"gradewise-executor-v1\n{timestamp}\n{hashlib.sha256(body).hexdigest()}".encode()
    key = serialization.load_pem_private_key(settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n").encode(), password=None)
    signature = base64.b64encode(key.sign(message, padding.PKCS1v15(), hashes.SHA256())).decode()
    async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
        response = await client.post(url, content=body, headers={
            "Content-Type": "application/json", "X-GradeWise-Time": timestamp,
            "X-GradeWise-Signature": signature,
        })
    if response.status_code != 200:
        raise RuntimeError(f"Isolated code runner unavailable (HTTP {response.status_code}); no simulated result used.")
    results = response.json().get("results")
    if not isinstance(results, list) or len(results) != len(inputs):
        raise RuntimeError("Code runner returned incomplete execution evidence.")
    for result in results:
        if result.get("isSimulated") is not False or not isinstance(result.get("exitCode"), int):
            raise RuntimeError("Code runner did not return real execution evidence.")
        if not isinstance(result.get("stdout"), str) or not isinstance(result.get("stderr"), str):
            raise RuntimeError("Code runner returned invalid output.")
    return results


async def verify_runner() -> None:
    import logging
    log = logging.getLogger(__name__)
    checks = [
        ("python", "print(int(input()) + 1)", ["41"], "42"),
        ("cpp", '#include <iostream>\nint main(){int x;std::cin>>x;std::cout<<x+1;}', ["41"], "42"),
        ("java", 'import java.util.Scanner; public class Main { public static void main(String[] a) { System.out.println(new Scanner(System.in).nextInt()+1); } }', ["41"], "42"),
    ]
    for language, code, inputs, expected in checks:
        result = (await execute_tests(code, language, inputs))[0]
        if result["exitCode"] != 0 or result["stdout"].strip() != expected:
            raise RuntimeError(f"{language} runner verification failed: {result['stderr'][:200]}")
        log.info("Real code verification passed: %s stdin/output (%sms)", language, result["durationMs"])
    result = (await execute_tests("while True: pass", "python", [""]))[0]
    if result["exitCode"] == 0 or not result.get("timedOut"):
        raise RuntimeError("Code execution timeout verification failed")
    log.info("Real code verification passed: infinite loop terminated")
    result = (await execute_tests("import socket\ntry:\n socket.create_connection(('1.1.1.1',443),timeout=1)\n print('unexpected network access')\nexcept OSError:\n print('network blocked')", "python", [""]))[0]
    if result["exitCode"] != 0 or result["stdout"].strip() != "network blocked":
        raise RuntimeError("Code execution network isolation verification failed")
    log.info("Real code verification passed: network blocked")

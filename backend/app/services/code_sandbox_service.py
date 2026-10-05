import os
import subprocess
import tempfile
import time
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("code_sandbox")

class CodeSandboxService:
    def __init__(self):
        self.timeout = getattr(settings, "SANDBOX_TIMEOUT_SECONDS", 5)
        self.memory_limit = f"{getattr(settings, 'SANDBOX_MEMORY_MB', 256)}m"
        self._init_docker()

    def _init_docker(self):
        if settings.DOCUMENT_DEMO or settings.CODE_RUNNER_URL or not settings.CODE_EXECUTION_ENABLED:
            self.docker_client = None
            self.has_docker = False
            return
        try:
            import docker
            self.docker_client = docker.from_env()
            # Simple ping to check if Docker daemon is active
            self.docker_client.ping()
            self.has_docker = True
            logger.info("Docker daemon successfully detected. Code Sandbox initialized.")
        except Exception as e:
            self.docker_client = None
            self.has_docker = False
            logger.warning(f"Docker is not available ({e}). Real code execution is unavailable.")

    async def execute_code(self, code_text: str, language: str, stdin_text: Optional[str] = None, zip_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes code inside a real isolated sandbox.
        Returns:
            Dict containing:
            - stdout: standard output from execution
            - stderr: compilation or runtime errors
            - exitCode: integer exit code
            - durationMs: time taken in milliseconds
            - isSimulated: boolean flag
        """
        from app.services.demo_limits import code_execution_available
        if not code_execution_available():
            raise RuntimeError("Code execution is paused on this deployment.")
        if settings.CODE_RUNNER_URL:
            if zip_path:
                raise RuntimeError("ZIP projects are paused on the demo runner.")
            from app.services.remote_code_runner import execute_tests
            return (await execute_tests(code_text, language, [stdin_text or ""]))[0]
        lang = language.lower()
        if lang not in ['python', 'cpp', 'java', 'c++']:
            return {
                "stdout": "",
                "stderr": f"Unsupported language: {language}",
                "exitCode": 1,
                "durationMs": 0,
                "isSimulated": False
            }

        # Normalize C++ language string
        if lang == 'c++':
            lang = 'cpp'

        logger.info(f"Initiating execution for {lang} code assignment...")

        # If Docker is available, attempt real sandboxed execution
        if self.has_docker and not getattr(settings, "USE_MOCKS", False):
            try:
                return await self._run_in_docker(code_text, lang, stdin_text, zip_path)
            except Exception as e:
                raise RuntimeError("Docker execution failed; no simulated result used.") from e

        # Fail closed when a real runner is unavailable
        raise RuntimeError("No real code runner is available; no simulated result used.")

    async def execute_tests(self, code_text: str, language: str, inputs: list[str], zip_path: Optional[str] = None) -> list[dict]:
        from app.services.demo_limits import code_execution_available
        if not code_execution_available():
            raise RuntimeError("Code execution is paused on this deployment.")
        if settings.CODE_RUNNER_URL:
            if zip_path:
                raise RuntimeError("ZIP projects are paused on the demo runner.")
            from app.services.remote_code_runner import execute_tests
            return await execute_tests(code_text, language, inputs)
        return [await self.execute_code(code_text, language, stdin_text=i, zip_path=zip_path) for i in inputs]

    async def _run_in_docker(self, code_text: str, lang: str, stdin_text: Optional[str] = None, zip_path: Optional[str] = None) -> Dict[str, Any]:
        # Ephemeral file storage
        with tempfile.TemporaryDirectory() as temp_dir:
            if zip_path and os.path.exists(zip_path):
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
            else:
                file_name = "solution.py" if lang == "python" else ("solution.cpp" if lang == "cpp" else "Main.java")
                host_file_path = os.path.join(temp_dir, file_name)
                with open(host_file_path, "w", encoding="utf-8") as f:
                    f.write(code_text)

            stdin_cmd = ""
            if stdin_text is not None:
                stdin_file_path = os.path.join(temp_dir, "stdin.txt")
                with open(stdin_file_path, "w", encoding="utf-8") as f:
                    f.write(stdin_text)
                stdin_cmd = " < /sandbox/stdin.txt"

            # Define image and commands based on language
            if lang == "python":
                image = "python:3.10-slim"
                cmd = f"sh -c 'if [ -f /sandbox/solution.py ]; then python /sandbox/solution.py{stdin_cmd}; elif [ -f /sandbox/main.py ]; then python /sandbox/main.py{stdin_cmd}; elif [ -f /sandbox/app.py ]; then python /sandbox/app.py{stdin_cmd}; else find /sandbox -name \"*.py\" | head -n 1 | xargs -I % python %{stdin_cmd}; fi'"
            elif lang == "cpp":
                image = "gcc:latest"
                cmd = f"sh -c 'find /sandbox -name \"*.cpp\" -o -name \"*.c\" | xargs g++ -o /sandbox/run && /sandbox/run{stdin_cmd}'"
            else: # java
                image = "eclipse-temurin:17-jdk"
                cmd = f"sh -c 'find /sandbox -name \"*.java\" > /sandbox/sources.txt && javac @/sandbox/sources.txt && java -cp /sandbox Main{stdin_cmd}'"

            # Mount temp folder inside container
            volumes = {temp_dir: {"bind": "/sandbox", "mode": "rw"}}
            
            start_time = time.time()
            try:
                # Spawn container in blocked execution
                container = self.docker_client.containers.create(
                    image=image,
                    command=cmd,
                    network_mode="none",
                    mem_limit=self.memory_limit,
                    volumes=volumes,
                    detach=True
                )
                
                container.start()
                
                # Enforce timeout manually
                result = None
                elapsed = 0.0
                while elapsed < self.timeout:
                    container.reload()
                    if container.status == 'exited':
                        result = container.wait()
                        break
                    time.sleep(0.2)
                    elapsed = time.time() - start_time
                
                # Check for timeout termination
                if not result:
                    container.kill()
                    return {
                        "stdout": "",
                        "stderr": f"Execution timed out after {self.timeout} seconds.",
                        "exitCode": -1,
                        "durationMs": int(elapsed * 1000),
                        "isSimulated": False
                    }
                    
                duration = int((time.time() - start_time) * 1000)
                logs = container.logs(stdout=True, stderr=False).decode("utf-8")
                err_logs = container.logs(stdout=False, stderr=True).decode("utf-8")
                
                # Clean container
                container.remove(force=True)
                
                return {
                    "stdout": logs,
                    "stderr": err_logs,
                    "exitCode": result.get("StatusCode", 0),
                    "durationMs": duration,
                    "isSimulated": False
                }
                
            except Exception as e:
                logger.error(f"Error executing in Docker container: {e}")
                raise e

# Initialize global instance
code_sandbox_service = CodeSandboxService()

"""
GradeWise — DOCX to PDF converter using LibreOffice headless.

LibreOffice preserves embedded images (screenshots, diagrams, figures) faithfully
through the DOCX→PDF conversion, which is not possible with pure Python DOCX parsers.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# DECISION: Use LibreOffice headless (soffice) for DOCX→PDF conversion.
# It correctly renders embedded images, tables, and complex layouts.
# Requires libreoffice installed in the Docker image.
SOFFICE_CMD = os.environ.get("SOFFICE_CMD", "soffice")


def convert(path: str) -> str:
    """
    Convert a DOCX (or DOC) file to PDF using LibreOffice headless.

    Returns the path to the generated PDF file.
    Raises RuntimeError if soffice is not available or conversion fails.
    """
    input_path = Path(path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    # Use a temp directory so LibreOffice doesn't write to the source dir
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = [
            SOFFICE_CMD,
            "--headless",
            "--norestore",
            "--convert-to", "pdf",
            "--outdir", tmp_dir,
            str(input_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "LibreOffice (soffice) is not installed or not in PATH. "
                "Add 'libreoffice' to your Dockerfile: RUN apt-get install -y libreoffice"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"LibreOffice conversion timed out for {path}")

        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice conversion failed (exit {result.returncode}): {result.stderr}"
            )

        # LibreOffice writes <basename>.pdf to the output dir
        pdf_name = input_path.stem + ".pdf"
        tmp_pdf = Path(tmp_dir) / pdf_name
        if not tmp_pdf.exists():
            raise RuntimeError(f"LibreOffice did not produce {pdf_name} in {tmp_dir}")

        # Move PDF to a stable temp file the caller can use
        import shutil
        stable_pdf = str(input_path.parent / pdf_name)
        shutil.copy2(str(tmp_pdf), stable_pdf)

    logger.info("DOCX→PDF: %s → %s", path, stable_pdf)
    return stable_pdf

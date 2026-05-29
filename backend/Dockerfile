FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: Tesseract for OCR baseline, curl for healthchecks, libreoffice for DOCX->PDF conversion.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      tesseract-ocr \
      libreoffice \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app

EXPOSE 8000

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for asyncpg (libpq is statically built in asyncpg, so minimal),
# Tesseract for OCR baseline, and curl for healthchecks/debug.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app

EXPOSE 8000

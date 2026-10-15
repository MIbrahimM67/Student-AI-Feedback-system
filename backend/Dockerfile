FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: curl for healthchecks, LibreOffice for DOCX->PDF, and an
# embedded Unicode PDF font for AI-generated grading evidence.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      libreoffice \
      fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app

EXPOSE 8000


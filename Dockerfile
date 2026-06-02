# Backend-only Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal build deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc git curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy only backend files (explicitly avoid copying the frontend/web folder)
COPY pyproject.toml /app/
COPY app.py /app/
COPY introlix /app/introlix

# Install the package and its dependencies
RUN pip install --no-cache-dir .

EXPOSE 7860

# Use port 7860 which is the default exposed port for Hugging Face Spaces
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

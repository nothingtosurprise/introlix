# Backend-only Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MAKEFLAGS="-j1"

WORKDIR /app

# Install minimal build deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc git curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*
    
# Reduce build parallelism and allow wheels when available
ENV MAKEFLAGS="-j1"

# Upgrade pip and packaging tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy only backend files (explicitly avoid copying the frontend/web folder)
COPY pyproject.toml /app/
# Remove local-only llama-cpp-python from pyproject during the HF build
# so the build installs dependencies from pyproject.toml but ignores
# the local-only `llama-cpp-python` dependency.
RUN sed '/llama-cpp-python/d' pyproject.toml > pyproject.tmp \
    && mv pyproject.tmp pyproject.toml \
    && pip install --no-cache-dir .

COPY app.py /app/
COPY introlix /app/introlix

EXPOSE 7860

# Use port 7860 which is the default exposed port for Hugging Face Spaces
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

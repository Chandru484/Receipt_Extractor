# Multi-platform production Dockerfile for Receipt Extractor API
# Compatible with Hugging Face Spaces (16GB RAM Free Tier), Render, Railway, Koyeb, and self-hosted Docker

FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    PADDLE_HOME=/app/.cache/paddle \
    PADDLE_PDX_CACHE_HOME=/app/.cache/paddlex

WORKDIR /app

# Install system libraries required by OpenCV, PaddleOCR, and PDF conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure cache directories exist with full read/write permissions for non-root containers
RUN mkdir -p /app/.cache/paddle /app/.cache/paddlex && chmod -R 777 /app/.cache

# Copy application code
COPY . .

# Expose default port (7860 for Hugging Face Spaces, or dynamic $PORT on Render/Railway)
EXPOSE 7860

# Launch Uvicorn, binding to $PORT if provided by the cloud platform, defaulting to 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]

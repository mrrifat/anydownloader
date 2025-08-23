# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies: ffmpeg for yt-dlp, ca-certificates
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app /app/app

# Create non-root user
RUN useradd -m runner
USER runner

EXPOSE 8000

# Gunicorn + Uvicorn workers
ENV WEB_CONCURRENCY=2
CMD ["bash", "-lc", "exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY} --timeout 180"]

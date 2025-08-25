FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps for yt-dlp/ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates curl build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app ./app            # your package folder
COPY main.py ./main.py    # your entry script at repo root
# If you keep .env in the repo root (NOT recommended for git):
# COPY .env ./.env

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

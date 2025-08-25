# main.py (root of the repo)
from __future__ import annotations
import os
import uuid
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from yt_dlp import YoutubeDL

# --- Load .env early (expects .env next to this file) ---
from dotenv import load_dotenv
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=False)

# --- Downloads directory (served at /api/downloads) ---
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/tmp/anygrab"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# --- Backblaze B2 (S3-compatible) env ---
def _env_bool(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")

B2_ENABLED         = _env_bool("B2_ENABLED", "false")
B2_KEY_ID          = os.getenv("B2_KEY_ID")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY")
B2_BUCKET_NAME     = os.getenv("B2_BUCKET_NAME")
B2_S3_ENDPOINT     = os.getenv("B2_S3_ENDPOINT", "https://s3.us-west-002.backblazeb2.com")
B2_PUBLIC_READ     = _env_bool("B2_PUBLIC_READ", "true")
B2_PUBLIC_BASE_URL = os.getenv("B2_PUBLIC_BASE_URL")  # optional CDN/website domain for public buckets
B2_PRESIGNED_TTL   = int(os.getenv("B2_PRESIGNED_TTL", "604800"))  # 7 days default

# --- yt-dlp cookies (optional, to bypass YouTube bot checks) ---
COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER")  # e.g. "chrome", "chrome:Default", "firefox:default"
COOKIES_FILE         = os.getenv("COOKIES_FILE")          # absolute path to cookies.txt

# --- Validate B2 env if enabled; set up client lazily ---
_b2_client = None
def _require_b2():
    if not B2_ENABLED:
        return
    missing = []
    if not B2_KEY_ID:          missing.append("B2_KEY_ID")
    if not B2_APPLICATION_KEY: missing.append("B2_APPLICATION_KEY")
    if not B2_BUCKET_NAME:     missing.append("B2_BUCKET_NAME")
    if missing:
        raise RuntimeError(f"Missing B2 env vars: {', '.join(missing)}")

def _b2():
    """Create (or reuse) a boto3 S3-compatible client for Backblaze B2."""
    global _b2_client
    if _b2_client is None:
        import boto3
        from botocore.client import Config
        _b2_client = boto3.client(
            "s3",
            endpoint_url=B2_S3_ENDPOINT,
            aws_access_key_id=B2_KEY_ID,
            aws_secret_access_key=B2_APPLICATION_KEY,
            config=Config(signature_version="s3v4"),
        )
    return _b2_client

def _b2_upload_and_url(local_path: Path) -> str:
    """Upload file to B2 and return a public or presigned URL."""
    client = _b2()
    object_key = f"uploads/{uuid.uuid4().hex}-{local_path.name}"
    content_type, _ = mimetypes.guess_type(local_path.name)
    extra = {"ContentType": content_type} if content_type else {}

    # Simple and reliable upload call
    with open(local_path, "rb") as fh:
        client.put_object(Bucket=B2_BUCKET_NAME, Key=object_key, Body=fh, **extra)

    if B2_PUBLIC_READ:
        base = B2_PUBLIC_BASE_URL or f"{B2_S3_ENDPOINT}/{B2_BUCKET_NAME}"
        return f"{base}/{object_key}"

    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": object_key},
        ExpiresIn=B2_PRESIGNED_TTL,
    )

# --- FastAPI app ---
app = FastAPI(
    title="AnyGrab API",
    description="Backend for AnyGrab (anygrab.xyz)",
    version="1.0.0",
)

# Expose local downloads via API path (Caddy proxies /api/* to us)
app.mount("/api/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

@app.on_event("startup")
async def _startup():
    # Fail fast if B2 is enabled but incomplete
    _require_b2()

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "AnyGrab", "b2_enabled": B2_ENABLED}

def _ydl_opts() -> Dict[str, Any]:
    """Build yt-dlp options with optional cookie settings from .env."""
    opts: Dict[str, Any] = {
        "outtmpl": str(DOWNLOAD_DIR / "%(title).60s-%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "merge_output_format": "mp4",
        "format": "bv*+ba/b",  # best video+audio; fallback to best
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    }

    # Optional cookie sources to bypass YouTube "bot" checks
    if COOKIES_FROM_BROWSER:
        parts = COOKIES_FROM_BROWSER.split(":", 1)
        browser = parts[0]
        profile = parts[1] if len(parts) > 1 else None
        opts["cookiesfrombrowser"] = (browser, None, profile)
    elif COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE

    return opts

def _extract_output_path(info: Dict[str, Any]) -> Optional[Path]:
    """yt-dlp returns file path in different shapes; normalize to a Path or None."""
    p = None
    try:
        if "requested_downloads" in info and info["requested_downloads"]:
            p = info["requested_downloads"][0].get("filepath")
        if not p:
            p = info.get("filepath")
    except Exception:
        p = None
    return Path(p) if p else None

def _local_download_url(local_file: Path) -> str:
    """Return the proxied URL for local files (Caddy → /api/*)."""
    return f"/api/downloads/{local_file.name}"

def _maybe_upload(local_file: Path) -> str:
    """Upload to B2 if enabled, else return local proxied URL."""
    if B2_ENABLED:
        return _b2_upload_and_url(local_file)
    return _local_download_url(local_file)

@app.post("/api/download-and-upload")
async def download_and_upload(payload: Dict[str, Any]):
    url = (payload or {}).get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'.")

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with YoutubeDL(_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        msg = str(e)
        # Friendly hint for common YouTube bot check
        if "confirm you’re not a bot" in msg.lower() or "confirm you're not a bot" in msg.lower():
            raise HTTPException(
                status_code=401,
                detail=(
                    "YouTube is requiring cookies. Set COOKIES_FROM_BROWSER "
                    "or COOKIES_FILE in .env and restart the server."
                ),
            )
        raise HTTPException(status_code=500, detail=f"yt-dlp error: {msg}")

    out_path = _extract_output_path(info)
    if not out_path or not out_path.exists():
        raise HTTPException(status_code=500, detail="Download succeeded but file path was not found.")

    # Try upload (if enabled); fall back to local URL if upload fails
    try:
        final_url = _maybe_upload(out_path)
    except Exception as e:
        if out_path.exists():
            final_url = _local_download_url(out_path)
        else:
            raise HTTPException(status_code=500, detail=f"B2 upload failed: {e}")

    return JSONResponse(
        {
            "source": "b2" if B2_ENABLED else "local",
            "url": final_url,
            "filename": out_path.name,
            "size_bytes": out_path.stat().st_size if out_path.exists() else None,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "id": info.get("id"),
        }
    )

# Optional: quick healthcheck to verify B2 creds without a real download
@app.post("/debug/b2")
async def debug_b2():
    if not B2_ENABLED:
        return {"enabled": False, "message": "B2 is disabled (set B2_ENABLED=true in .env)"}
    _require_b2()
    test_key = f"healthcheck/{uuid.uuid4().hex}.txt"
    body = b"ok"
    try:
        _b2().put_object(Bucket=B2_BUCKET_NAME, Key=test_key, Body=body)
        if B2_PUBLIC_READ:
            base = B2_PUBLIC_BASE_URL or f"{B2_S3_ENDPOINT}/{B2_BUCKET_NAME}"
            url = f"{base}/{test_key}"
        else:
            url = _b2().generate_presigned_url(
                "get_object",
                Params={"Bucket": B2_BUCKET_NAME, "Key": test_key},
                ExpiresIn=min(B2_PRESIGNED_TTL, 300),
            )
        return {"enabled": True, "bucket": B2_BUCKET_NAME, "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"B2 healthcheck failed: {e}")

import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from starlette.concurrency import run_in_threadpool

# yt-dlp
import yt_dlp

# Backblaze B2 SDK
from b2sdk.v2 import InMemoryAccountInfo, B2Api


# ---------- Config ----------
B2_KEY_ID = os.getenv("B2_KEY_ID")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")

if not all([B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME]):
    raise RuntimeError("Missing Backblaze B2 env vars: B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME")

# Disable yt-dlp auto-updater for reproducible builds
os.environ.setdefault("YT_DLP_DISABLE_UPDATE", "1")

app = FastAPI(title="Any Downloader API", version="1.0.0")

# CORS (scoped to your domain; loosen to ["*"] if you need)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dw.fil-bd.com", "http://dw.fil-bd.com"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Models ----------
class DownloadRequest(BaseModel):
    url: HttpUrl


class DownloadResponse(BaseModel):
    downloadUrl: HttpUrl


# ---------- Helpers ----------
def _download_video_to_temp(url: str) -> Path:
    """
    Download video with yt-dlp into a temporary folder.
    Returns the path to the final file.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="anydownloader_"))
    outtmpl = str(tmpdir / "%(title).200B-%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "merge_output_format": "mp4",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            candidate = Path(filename)

            if not candidate.exists():
                # try post-merge .mp4
                candidate_mp4 = candidate.with_suffix(".mp4")
                if candidate_mp4.exists():
                    candidate = candidate_mp4
                else:
                    files = sorted(tmpdir.glob("*"), key=lambda p: p.stat().st_size, reverse=True)
                    if not files:
                        raise FileNotFoundError("Downloaded file not found")
                    candidate = files[0]
            return candidate
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise


def _b2_client() -> B2Api:
    info = InMemoryAccountInfo()
    api = B2Api(info)
    api.authorize_account("production", B2_KEY_ID, B2_APPLICATION_KEY)
    return api


def _upload_to_b2_and_get_signed_url(filepath: Path) -> str:
    """
    Upload the file to Backblaze B2 and return a 1-hour temporary link.
    Uses download authorization token as a query parameter for browser-friendly access.
    """
    api = _b2_client()
    bucket = api.get_bucket_by_name(B2_BUCKET_NAME)

    today = datetime.utcnow().strftime("%Y/%m/%d")
    dest_name = f"videos/{today}/{uuid.uuid4().hex}-{filepath.name}"

    bucket.upload_local_file(local_file=str(filepath), file_name=dest_name)

    base_url = api.get_download_url_for_file_name(B2_BUCKET_NAME, dest_name)
    token = bucket.get_download_authorization(
        file_name_prefix=dest_name,
        valid_duration_in_seconds=3600,
    )

    from urllib.parse import urlencode
    signed = f"{base_url}?{urlencode({'Authorization': token})}"
    return signed


async def _process(url: str) -> str:
    path: Optional[Path] = None
    try:
        path = await run_in_threadpool(_download_video_to_temp, url)
        signed_url = await run_in_threadpool(_upload_to_b2_and_get_signed_url, path)
        return signed_url
    finally:
        if path:
            try:
                shutil.rmtree(path.parent, ignore_errors=True)
            except Exception:
                pass


# ---------- API ----------
@app.post("/api/download-and-upload", response_model=DownloadResponse)
async def download_and_upload(payload: DownloadRequest):
    try:
        signed_url = await _process(payload.url)
        return DownloadResponse(downloadUrl=signed_url)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Download error: {str(e)[:300]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)[:300]}")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Static (mounted last so /api/* always wins) ----------
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

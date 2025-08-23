# Any Downloader — FastAPI + Backblaze B2 Video Downloader

Production-ready single-page app:

- **Frontend**: HTML + Tailwind (Purple Neon, glassmorphism, dark/light mode)
- **Backend**: FastAPI + `yt-dlp` + Backblaze B2 (`b2sdk`)
- **Infra**: Docker, Nginx reverse proxy, TLS via Certbot

---

## 1) Prerequisites

- Ubuntu 22.04+ VPS with root (or sudo) access
- DNS `A` record for **dw.fil-bd.com** pointing to your VPS IP
- Docker & Docker Compose installed

```bash
# Install Docker Engine + Compose plugin:
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --yes --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Optionally:

```bash
sudo usermod -aG docker $USER
# re-login for group change to take effect
```

---

## 2) Project layout

```
.
├─ app/
│  ├─ main.py
│  └─ static/
│     └─ index.html
├─ nginx/
│  └─ nginx.conf
├─ certbot/
│  └─ www/                # webroot for ACME challenges (auto-created)
├─ letsencrypt/           # certificates volume (auto-created)
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
└─ README.md
```

---

## 3) Build & run (first time)

1. **Clone or upload** these files to your VPS (e.g., in `/opt/anydownloader`).

2. **Obtain initial TLS certificate** (HTTP-01 webroot):

```bash
docker compose pull
docker compose up -d nginx
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d dw.fil-bd.com \
  --email you@example.com --agree-tos --no-eff-email
```

> If this succeeds, `fullchain.pem` and `privkey.pem` will appear under `./letsencrypt/live/dw.fil-bd.com/`.

3. **Start the full stack**:

```bash
docker compose up -d --build
```

4. Open **[https://dw.fil-bd.com](https://dw.fil-bd.com)** in your browser.

Renewals run inside the `certbot` service every 12 hours and Nginx loads the files from the shared volume.

---

## 4) How it works

* The frontend posts `{"url": "..."}` to `POST /api/download-and-upload`.
* The backend downloads the video with `yt-dlp` to a temp file, uploads it to **Backblaze B2**, and returns a **1-hour temporary link**.
* Temporary links are generated with **Backblaze download authorization tokens** appended as a query parameter, so they work directly in browsers.

---

## 5) Environment variables

In this sample, the credentials are in `docker-compose.yml` for simplicity:

```yaml
B2_KEY_ID: "0035e6a5a1dfb350000000001"
B2_APPLICATION_KEY: "K003kVlMeHzb35LXMtbC3vERRUh4m5w"
B2_BUCKET_NAME: "anydownloader"
```

**Recommended (safer) approach**: create a `.env` file and reference it:

```bash
cat > .env << 'EOF'
B2_KEY_ID=0035e6a5a1dfb350000000001
B2_APPLICATION_KEY=K003kVlMeHzb35LXMtbC3vERRUh4m5w
B2_BUCKET_NAME=anydownloader
WEB_CONCURRENCY=2
EOF
```

Then in `docker-compose.yml`:

```yaml
  web:
    env_file:
      - .env
```

Rotate secrets if they have been shared or committed.

---

## 6) Firewall

On Ubuntu with UFW:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

---

## 7) Operations

* **Logs**: `docker compose logs -f web` or `nginx` or `certbot`
* **Rebuild** after edits: `docker compose up -d --build`
* **Update yt-dlp**: rebuild the image (we disable auto-update for reproducibility)
* **Health check**: `GET https://dw.fil-bd.com/health` → `{"status":"ok"}`

---

## 8) Troubleshooting

* **TLS issuance fails**: Verify DNS points to the VPS and port 80 is open. The `nginx` service must be running before you run the `certbot certonly` command.
* **Download fails**: Some hosts may block scraping or need cookies/headers. You can extend `yt-dlp` options in `app/main.py`.
* **Large videos**: Increase Gunicorn `--timeout` or move downloads/uploads to a background worker.
* **CORS**: CORS is open to `https://dw.fil-bd.com`. If you want looser testing, allow `*`.

---

## 9) Notes

* Native Backblaze **download authorization** tokens can be supplied as an `Authorization` query parameter, which makes them browser-friendly (no headers required).
* The backend automatically deletes temp files after each upload.

---

## 10) License

MIT (do what you want, no warranty).

```

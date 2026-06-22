# ☁️ CloudDrive — Personal Cloud Storage

A self-hosted, Google-Drive-style personal storage app. FastAPI backend,
SQLite database, vanilla HTML/CSS/JS frontend. Single admin login (no
signup), folders, chunked resumable uploads up to 100GB+, streamed
downloads, search, and a storage quota.

---

## 1. Folder structure

```
clouddrive/
├── app/
│   ├── __init__.py
│   ├── config.py            # env settings (.env loader)
│   ├── database.py          # SQLite connection + schema
│   ├── auth.py               # admin-password auth + JWT
│   ├── schemas.py            # Pydantic request/response models
│   ├── storage.py            # disk helpers (quota calc, delete, search)
│   └── routers/
│       ├── auth_router.py    # POST /api/auth/login
│       ├── folders_router.py # folder create/browse/delete
│       └── files_router.py   # upload, download, delete, search, quota
├── frontend/
│   ├── index.html
│   └── static/
│       ├── css/style.css
│       └── js/
│           ├── api.js        # fetch wrapper + auth token
│           ├── upload.js     # chunked resumable upload + streamed download
│           └── app.js        # UI rendering + event wiring
├── data/                      # created at runtime — NOT committed
│   ├── storage/                # actual uploaded files live here
│   ├── db/clouddrive.db        # SQLite database file
│   └── temp_chunks/            # in-progress chunked uploads
├── main.py                    # FastAPI entrypoint
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 2. Database schema

Four tables, no ORM — plain SQL, easy to inspect with `sqlite3 data/db/clouddrive.db`.

| Table             | Purpose                                                              |
|-------------------|-----------------------------------------------------------------------|
| `folders`         | Tree structure. `parent_id IS NULL` = root level.                    |
| `files`           | One row per completed, browsable file. `storage_name` is the real filename on disk (uuid-prefixed so name collisions never matter). |
| `upload_sessions` | One row per chunked upload in progress. Tracks total size, chunk size, status. |
| `upload_chunks`   | One row per chunk that has successfully landed on disk. **This table is what makes resume work** — on reconnect the client asks "what do you have?" and this table answers. |

See `app/database.py` for the full `CREATE TABLE` statements with all constraints/indexes.

---

## 3. How the big-file features actually work

**Chunked upload (100GB-safe):**
The browser never holds the whole file in memory. `File.slice()` creates a
lazy view into a piece of the file, which gets PUT to
`/api/files/upload/chunk` one piece at a time (8MB by default,
configurable via `CHUNK_SIZE_BYTES`). The server streams that piece
straight to a chunk file on disk in 256KB reads — so RAM usage stays flat
whether the file is 8MB or 800GB.

**Resume after interruption:**
Every chunk that lands on disk gets a row in `upload_chunks`. If the
upload dies (closed tab, dropped wifi, server restart), the client calls
`GET /api/files/upload/status?session_id=...`, gets back the list of
chunk indices already saved, and only (re)sends what's missing. The
upload picks up exactly where it left off instead of restarting.

**Streamed download with Range support:**
`GET /api/files/download/{id}` reads the file off disk in 1MB pieces via
`StreamingResponse` — again, the whole file is never in memory at once.
It also honours `Range: bytes=...` headers, which is what lets the
frontend's progress bar work, lets download managers resume a dropped
download, and lets a browser's native `<video>` player seek.

**Storage quota:**
Checked at upload-init time and again right before the chunks get
assembled into the final file (in case other uploads finished in
between and ate the headroom). Set via `STORAGE_QUOTA_GB` in `.env`.

---

## 4. Installation — running directly with Python

### Requirements
- Python 3.10+
- ~50MB free disk for the app itself (your actual storage quota is separate)

### Steps

```bash
# 1. Get the code into a folder, then cd into it
cd clouddrive

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file from the example and edit it
cp .env.example .env
nano .env     # set ADMIN_PASSWORD and JWT_SECRET at minimum

# Generate a real random JWT secret with:
python -c "import secrets; print(secrets.token_hex(32))"

# 5. Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 120
```

Open **http://localhost:8000** in your browser, log in with the
username/password you set in `.env`.

> `--timeout-keep-alive 120` is important if you'll be uploading very
> large files over a slow connection — it stops the server from closing
> an idle-looking connection mid chunk-upload.

### Running it in the background (Linux, simple way)

```bash
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 120 > clouddrive.log 2>&1 &
```

For a proper production setup, put it behind `systemd` or `supervisord`,
and put nginx/Caddy in front of it for TLS (see section 6).

---

## 5. Installation — Docker (optional, as requested)

```bash
cd clouddrive
cp .env.example .env
nano .env   # set ADMIN_PASSWORD and JWT_SECRET

docker compose up -d --build
```

That's it — the compose file reads the same `.env` file and mounts
`./data` on the host so your files/database survive container rebuilds.

To stop: `docker compose down`
To see logs: `docker compose logs -f`

If you plan to actually push 100GB files through this, point the `./data`
bind mount in `docker-compose.yml` at a disk that has the room — Docker
volumes don't grow disk space, they just point at wherever you mount them.

---

## 6. Handling files up to 100GB in production (important notes)

1. **Reverse proxy body-size limits.** If you put nginx in front of this,
   you need `client_max_body_size 0;` (unlimited) or a number ≥ your
   largest expected *chunk* — note chunks are only 8MB by default, so
   this mostly matters if you raise `CHUNK_SIZE_BYTES` a lot. The overall
   100GB file is never sent as one request, so the usual nginx upload
   limit isn't really in play, but set it generously anyway.
2. **Disk space.** SQLite just stores metadata (tiny). The actual bytes
   go to `STORAGE_PATH`. Make sure that disk/mount has room — checking
   `df -h` before pointing this at a big upload is wise.
3. **Browser tab must stay open during upload.** This is a plain
   client-side JS uploader, not a background OS-level uploader — if you
   close the tab mid-upload, it stops, but it *resumes cleanly* next time
   you pick the same file and click upload again (see section 3).

---

## 7. API reference (quick)

All endpoints except `/api/auth/login` require `Authorization: Bearer <token>`
(or `?token=<token>` for plain download links).

| Method | Path                              | Purpose                                |
|--------|------------------------------------|------------------------------------------|
| POST   | `/api/auth/login`                  | Log in, returns JWT                      |
| GET    | `/api/folders/browse?folder_id=`   | List folders+files in a folder           |
| POST   | `/api/folders`                     | Create folder `{name, parent_id}`        |
| DELETE | `/api/folders/{id}`                | Delete folder (recursively)              |
| GET    | `/api/files/quota`                 | Storage usage stats                      |
| GET    | `/api/files/search?q=`             | Search files by name                     |
| POST   | `/api/files/upload/init`           | Start a chunked upload, get session_id   |
| GET    | `/api/files/upload/status?session_id=` | Which chunks are already on disk    |
| PUT    | `/api/files/upload/chunk`           | Upload one chunk (multipart form)        |
| POST   | `/api/files/upload/complete?session_id=` | Assemble chunks into final file    |
| DELETE | `/api/files/upload/{session_id}`    | Abort/cancel an in-progress upload       |
| GET    | `/api/files/download/{id}`          | Stream-download a file (Range supported) |
| DELETE | `/api/files/{id}`                   | Delete a file                            |

Interactive Swagger docs are also auto-generated at **`/docs`**.

---

## 8. Security notes

- This app is designed for **single-user / personal use** (e.g. on your
  home network or a small VPS you control). There's no rate-limiting on
  the login endpoint — if you expose it to the public internet, put it
  behind a reverse proxy with rate limiting, and use HTTPS.
- Change `JWT_SECRET` and `ADMIN_PASSWORD` from the defaults before
  running this anywhere other than your own machine for testing.
- CORS is wide open (`allow_origins=["*"]`) in `main.py` for convenience —
  tighten it if you deploy this somewhere reachable by others.

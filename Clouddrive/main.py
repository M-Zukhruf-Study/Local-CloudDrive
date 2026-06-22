"""
Entry point. Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000

Wires up the API routers, serves the static frontend (HTML/CSS/JS), and
initialises the SQLite schema on startup.
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.database import init_db
from app.routers import auth_router, folders_router, files_router
from app.config import settings

app = FastAPI(title="CloudDrive", version="1.0.0")

# Allow the app to be accessed from the local network and from browsers that
# may send different host headers.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],
)

# CORS is wide open here because this is a personal single-user app typically
# run on a LAN/behind a reverse proxy. Tighten allow_origins if you expose
# this publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(folders_router.router)
app.include_router(files_router.router)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def serve_frontend():
    return FileResponse("frontend/index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        timeout_keep_alive=120,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )

"""
The heart of the app: chunked + resumable uploads, and streamed downloads.

Upload flow (how resume actually works):
  1. POST /api/files/upload/init      -> creates an upload_sessions row,
                                          a temp folder, returns session_id
                                          + any chunk indices already on disk
                                          (0 on a fresh upload, non-empty if
                                          the client is resuming after a crash
                                          and calls init again with a session
                                          it already has... see /status below
                                          for the normal resume path).
  2. PUT  /api/files/upload/chunk     -> client sends ONE chunk + its index.
                                          Saved as <temp_path>/chunk_<index>.
                                          Row inserted into upload_chunks.
  3. GET  /api/files/upload/status    -> "which chunks do you already have?"
                                          Client calls this on reconnect/retry
                                          and only (re)sends what's missing.
  4. POST /api/files/upload/complete  -> server concatenates all chunk files
                                          in order into the final storage
                                          file, verifies size, writes the
                                          `files` row, deletes temp chunks.

Download: streamed in 1MB pieces via StreamingResponse so a 100GB file
never has to sit in memory, and HTTP Range requests are honoured so
browsers/players can seek and resumable download managers work too.
"""
import os
import uuid
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse

from app.auth import get_current_user
from app.database import db_cursor
from app.config import settings
from app.schemas import (
    InitUploadRequest, InitUploadResponse, ChunkStatusResponse,
    CompleteUploadResponse, FileOut, QuotaResponse,
)
from app.storage import (
    get_used_bytes, delete_single_file, search_files, physical_path,
)

router = APIRouter(prefix="/api/files", tags=["files"])

STREAM_CHUNK = 1024 * 1024  # 1MB read size for downloads


# ---------------------------------------------------------------- quota ----

@router.get("/quota", response_model=QuotaResponse)
def quota(user: str = Depends(get_current_user)):
    with db_cursor() as cur:
        from app.storage import sync_storage_state
        sync_storage_state(cur)
        used = get_used_bytes(cur)
    total = settings.storage_quota_bytes
    return QuotaResponse(
        used_bytes=used,
        quota_bytes=total,
        used_gb=round(used / (1024 ** 3), 3),
        quota_gb=round(total / (1024 ** 3), 3),
        percent_used=round((used / total) * 100, 2) if total else 0.0,
    )


# ------------------------------------------------------ chunked upload ----

@router.post("/upload/init", response_model=InitUploadResponse)
def init_upload(payload: InitUploadRequest, user: str = Depends(get_current_user)):
    with db_cursor() as cur:
        if payload.folder_id is not None:
            exists = cur.execute(
                "SELECT id FROM folders WHERE id = ?", (payload.folder_id,)
            ).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Folder not found")

        used = get_used_bytes(cur)
        if used + payload.total_size > settings.storage_quota_bytes:
            raise HTTPException(status_code=413, detail="Storage quota exceeded")

        dup = cur.execute(
            "SELECT id FROM files WHERE folder_id IS ? AND name = ?",
            (payload.folder_id, payload.file_name),
        ).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail="A file with this name already exists here")

        session_id = str(uuid.uuid4())
        total_chunks = max(1, -(-payload.total_size // payload.chunk_size))  # ceil div
        temp_path = str(Path(settings.temp_chunk_path) / session_id)
        Path(temp_path).mkdir(parents=True, exist_ok=True)

        cur.execute(
            """INSERT INTO upload_sessions
               (id, file_name, folder_id, total_size, chunk_size, total_chunks, mime_type, temp_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'uploading')""",
            (session_id, payload.file_name, payload.folder_id, payload.total_size,
             payload.chunk_size, total_chunks, payload.mime_type, temp_path),
        )

    return InitUploadResponse(session_id=session_id, total_chunks=total_chunks, uploaded_chunks=[])


@router.get("/upload/status", response_model=ChunkStatusResponse)
def upload_status(session_id: str, user: str = Depends(get_current_user)):
    """
    The frontend calls this whenever it (re)starts an upload it has a
    session_id for — after a refresh, a dropped connection, closing the
    laptop, whatever. It gets back exactly which chunk indices are already
    safely on disk and only uploads the rest.
    """
    with db_cursor() as cur:
        session = cur.execute(
            "SELECT * FROM upload_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Upload session not found")

        chunk_rows = cur.execute(
            "SELECT chunk_index FROM upload_chunks WHERE session_id = ? ORDER BY chunk_index",
            (session_id,),
        ).fetchall()
        uploaded = [r["chunk_index"] for r in chunk_rows]

    return ChunkStatusResponse(
        session_id=session_id,
        uploaded_chunks=uploaded,
        total_chunks=session["total_chunks"],
        status=session["status"],
    )


@router.put("/upload/chunk")
async def upload_chunk(
    session_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    user: str = Depends(get_current_user),
):
    with db_cursor() as cur:
        session = cur.execute(
            "SELECT * FROM upload_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Upload session not found")
        if session["status"] != "uploading":
            raise HTTPException(status_code=400, detail=f"Session is {session['status']}, not accepting chunks")
        if chunk_index < 0 or chunk_index >= session["total_chunks"]:
            raise HTTPException(status_code=400, detail="chunk_index out of range")

    # Write the chunk to <temp_path>/chunk_<index>. Stream straight to disk
    # in small reads so even an 8MB+ chunk never fully sits in RAM.
    chunk_path = Path(session["temp_path"]) / f"chunk_{chunk_index:08d}"
    size_written = 0
    with open(chunk_path, "wb") as out:
        while True:
            piece = await chunk.read(1024 * 256)
            if not piece:
                break
            out.write(piece)
            size_written += len(piece)

    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO upload_chunks (session_id, chunk_index, size_bytes)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id, chunk_index) DO UPDATE SET size_bytes = excluded.size_bytes""",
            (session_id, chunk_index, size_written),
        )
        cur.execute(
            "UPDATE upload_sessions SET updated_at = datetime('now') WHERE id = ?",
            (session_id,),
        )

    return {"detail": "Chunk received", "chunk_index": chunk_index, "size_bytes": size_written}


@router.post("/upload/complete", response_model=CompleteUploadResponse)
def complete_upload(session_id: str, user: str = Depends(get_current_user)):
    with db_cursor() as cur:
        session = cur.execute(
            "SELECT * FROM upload_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Upload session not found")

        # Make repeated completion requests idempotent.
        if session["status"] == "completed":
            existing = cur.execute(
                """
                SELECT id, name, folder_id, size_bytes, mime_type, created_at
                FROM files
                WHERE name = ?
                  AND ((folder_id = ?) OR (folder_id IS NULL AND ? IS NULL))
                  AND size_bytes = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (session["file_name"], session["folder_id"], session["folder_id"], session["total_size"]),
            ).fetchone()
            if existing:
                return CompleteUploadResponse(file=FileOut(**dict(existing)))

        if session["status"] != "uploading":
            raise HTTPException(
                status_code=409,
                detail=f"Upload session is already {session['status']}",
            )

        # Prevent two concurrent completion requests from racing each other.
        updated = cur.execute(
            "UPDATE upload_sessions SET status = 'completing' WHERE id = ? AND status = 'uploading'",
            (session_id,),
        ).rowcount
        if updated != 1:
            raise HTTPException(
                status_code=409,
                detail="Upload completion already in progress",
            )

        chunk_rows = cur.execute(
            "SELECT chunk_index, size_bytes FROM upload_chunks WHERE session_id = ? ORDER BY chunk_index",
            (session_id,),
        ).fetchall()
        have = {r["chunk_index"] for r in chunk_rows}
        expected = set(range(session["total_chunks"]))
        missing = sorted(expected - have)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot complete: missing {len(missing)} chunk(s), e.g. {missing[:5]}",
            )

        # Re-check quota at completion time too (in case other uploads
        # finished in the meantime and ate the headroom).
        used = get_used_bytes(cur)
        if used + session["total_size"] > settings.storage_quota_bytes:
            raise HTTPException(status_code=413, detail="Storage quota exceeded")

        safe_name = Path(session["file_name"]).name
        storage_name = f"{session_id}_{safe_name}"
        final_path = physical_path(storage_name)

        # Concatenate chunks, in order, into the final file.
        total_written = 0
        with open(final_path, "wb") as out_file:
            for idx in range(session["total_chunks"]):
                part_path = Path(session["temp_path"]) / f"chunk_{idx:08d}"
                with open(part_path, "rb") as part:
                    while True:
                        buf = part.read(1024 * 1024)
                        if not buf:
                            break
                        out_file.write(buf)
                        total_written += len(buf)

        if total_written != session["total_size"]:
            # Don't leave a half-written file lying around or a stale DB row.
            try:
                os.remove(final_path)
            except OSError:
                pass
            raise HTTPException(
                status_code=400,
                detail=f"Size mismatch after assembly: expected {session['total_size']}, got {total_written}",
            )

        mime_type = session["mime_type"] or mimetypes.guess_type(session["file_name"])[0] or "application/octet-stream"

        cur.execute(
            """INSERT OR IGNORE INTO files (name, folder_id, size_bytes, mime_type, storage_name)
               VALUES (?, ?, ?, ?, ?)""",
            (session["file_name"], session["folder_id"], total_written, mime_type, storage_name),
        )
        existing = cur.execute(
            "SELECT id, name, folder_id, size_bytes, mime_type, created_at FROM files WHERE storage_name = ?",
            (storage_name,),
        ).fetchone()
        if not existing:
            existing = cur.execute(
                """
                SELECT id, name, folder_id, size_bytes, mime_type, created_at
                FROM files
                WHERE name = ?
                  AND ((folder_id = ?) OR (folder_id IS NULL AND ? IS NULL))
                  AND size_bytes = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (session["file_name"], session["folder_id"], session["folder_id"], total_written),
            ).fetchone()

        cur.execute("UPDATE upload_sessions SET status = 'completed' WHERE id = ?", (session_id,))

        row = existing

    # Clean up the temp chunk folder now that bytes are safely consolidated.
    _cleanup_temp_dir(session["temp_path"])

    return CompleteUploadResponse(file=FileOut(**dict(row)))


@router.delete("/upload/{session_id}")
def abort_upload(session_id: str, user: str = Depends(get_current_user)):
    with db_cursor() as cur:
        session = cur.execute(
            "SELECT * FROM upload_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Upload session not found")
        cur.execute("UPDATE upload_sessions SET status = 'aborted' WHERE id = ?", (session_id,))
    _cleanup_temp_dir(session["temp_path"])
    return {"detail": "Upload aborted"}


def _cleanup_temp_dir(temp_path: str):
    try:
        folder = Path(temp_path)
        for f in folder.glob("chunk_*"):
            f.unlink(missing_ok=True)
        folder.rmdir()
    except OSError:
        pass


# -------------------------------------------------------------- search ----

@router.get("/search", response_model=list[FileOut])
def search(q: str, user: str = Depends(get_current_user)):
    if not q or len(q.strip()) == 0:
        return []
    with db_cursor() as cur:
        rows = search_files(cur, q.strip())
    return [FileOut(**dict(r)) for r in rows]


# -------------------------------------------------------------- delete ----

@router.delete("/{file_id}")
def delete_file(file_id: int, user: str = Depends(get_current_user)):
    with db_cursor() as cur:
        row = cur.execute("SELECT id FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        delete_single_file(cur, file_id)
    return {"detail": "File deleted"}


# ------------------------------------------------------------ download ----

@router.get("/download/{file_id}")
def download_file(file_id: int, request: Request, user: str = Depends(get_current_user)):
    """
    Streamed download with HTTP Range support. Range support is what lets
    browsers show a real progress bar/ETA, lets video/audio elements seek,
    and lets download managers resume a dropped download — the same
    mechanism Drive, YouTube, etc. all rely on.
    """
    with db_cursor() as cur:
        row = cur.execute(
            "SELECT name, size_bytes, mime_type, storage_name FROM files WHERE id = ?",
            (file_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")

    path = physical_path(row["storage_name"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")

    file_size = row["size_bytes"]
    mime_type = row["mime_type"] or "application/octet-stream"
    range_header = request.headers.get("range")

    def iter_range(start: int, end: int):
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                read_size = min(STREAM_CHUNK, remaining)
                data = f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Disposition": f'attachment; filename="{row["name"]}"',
        "Accept-Ranges": "bytes",
    }

    if range_header:
        try:
            range_value = range_header.replace("bytes=", "").split("-")
            start = int(range_value[0]) if range_value[0] else 0
            end = int(range_value[1]) if len(range_value) > 1 and range_value[1] else file_size - 1
        except (ValueError, IndexError):
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(end - start + 1)

        return StreamingResponse(
            iter_range(start, end),
            status_code=206,
            media_type=mime_type,
            headers=headers,
        )

    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        iter_range(0, file_size - 1),
        status_code=200,
        media_type=mime_type,
        headers=headers,
    )

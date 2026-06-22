"""
Helpers that touch both the DB and the actual filesystem under storage_path.
Kept separate from the routers so folders_router / files_router don't need
to duplicate this logic.
"""
import os
import mimetypes
from pathlib import Path
from app.config import settings


def physical_path(storage_name: str) -> Path:
    return Path(settings.storage_path) / storage_name


def get_used_bytes(cur) -> int:
    row = cur.execute("SELECT COALESCE(SUM(size_bytes), 0) AS total FROM files").fetchone()
    return int(row["total"])


def sync_storage_state(cur):
    """
    Keep the DB in sync with files that were added/removed directly on disk.
    This lets manual copy/paste or deletion outside the app still appear
    correctly after the next browse or refresh.
    """
    storage_root = Path(settings.storage_path)
    storage_root.mkdir(parents=True, exist_ok=True)

    # Remove DB entries whose physical file is no longer present.
    rows = cur.execute("SELECT id, storage_name FROM files").fetchall()
    for row in rows:
        if not physical_path(row["storage_name"]).exists():
            cur.execute("DELETE FROM files WHERE id = ?", (row["id"],))

    # Add any files that exist on disk but are missing from the DB.
    existing_storage_names = {
        r["storage_name"] for r in cur.execute("SELECT storage_name FROM files")
    }
    for path in storage_root.iterdir():
        if not path.is_file() or path.name in existing_storage_names:
            continue
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        cur.execute(
            "INSERT OR IGNORE INTO files (name, folder_id, size_bytes, mime_type, storage_name) VALUES (?, ?, ?, ?, ?)",
            (path.name, None, path.stat().st_size, mime_type, path.name),
        )


def delete_files_under_folder(cur, folder_id: int):
    """
    Recursively find every file under folder_id (including nested
    subfolders) and remove the actual bytes from disk. The DB rows
    themselves are cleaned up afterwards by ON DELETE CASCADE when the
    caller deletes the folder.
    """
    # Collect this folder + all descendant folder ids.
    to_visit = [folder_id]
    all_folder_ids = []
    while to_visit:
        current = to_visit.pop()
        all_folder_ids.append(current)
        children = cur.execute(
            "SELECT id FROM folders WHERE parent_id = ?", (current,)
        ).fetchall()
        to_visit.extend(c["id"] for c in children)

    placeholders = ",".join("?" * len(all_folder_ids))
    rows = cur.execute(
        f"SELECT storage_name FROM files WHERE folder_id IN ({placeholders})",
        all_folder_ids,
    ).fetchall()

    for row in rows:
        path = physical_path(row["storage_name"])
        try:
            if path.exists():
                os.remove(path)
        except OSError:
            pass  # best-effort; DB cleanup still proceeds


def delete_single_file(cur, file_id: int):
    row = cur.execute("SELECT storage_name FROM files WHERE id = ?", (file_id,)).fetchone()
    if row:
        path = physical_path(row["storage_name"])
        try:
            if path.exists():
                os.remove(path)
        except OSError:
            pass
    cur.execute("DELETE FROM files WHERE id = ?", (file_id,))


def search_files(cur, query: str):
    like = f"%{query}%"
    rows = cur.execute(
        "SELECT id, name, folder_id, size_bytes, mime_type, created_at FROM files "
        "WHERE name LIKE ? ORDER BY name COLLATE NOCASE LIMIT 200",
        (like,),
    ).fetchall()
    return rows

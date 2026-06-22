from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from app.auth import get_current_user
from app.database import db_cursor
from app.schemas import FolderCreate, FolderOut, BrowseResponse, FileOut

router = APIRouter(prefix="/api/folders", tags=["folders"])


def _build_breadcrumb(cur, folder_id: Optional[int]) -> list[dict]:
    """Walk parent_id up to the root, return root-first list."""
    trail = []
    current_id = folder_id
    while current_id is not None:
        row = cur.execute(
            "SELECT id, name, parent_id, created_at FROM folders WHERE id = ?",
            (current_id,),
        ).fetchone()
        if row is None:
            break
        trail.append(dict(row))
        current_id = row["parent_id"]
    trail.reverse()
    return trail


@router.post("", response_model=FolderOut)
def create_folder(payload: FolderCreate, user: str = Depends(get_current_user)):
    with db_cursor() as cur:
        if payload.parent_id is not None:
            exists = cur.execute(
                "SELECT id FROM folders WHERE id = ?", (payload.parent_id,)
            ).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Parent folder not found")

        dup = cur.execute(
            "SELECT id FROM folders WHERE parent_id IS ? AND name = ?",
            (payload.parent_id, payload.name),
        ).fetchone()
        if dup:
            raise HTTPException(status_code=409, detail="A folder with this name already exists here")

        cur.execute(
            "INSERT INTO folders (name, parent_id) VALUES (?, ?)",
            (payload.name, payload.parent_id),
        )
        new_id = cur.lastrowid
        row = cur.execute(
            "SELECT id, name, parent_id, created_at FROM folders WHERE id = ?",
            (new_id,),
        ).fetchone()
        return FolderOut(**dict(row))


@router.get("/browse", response_model=BrowseResponse)
def browse(folder_id: Optional[int] = None, user: str = Depends(get_current_user)):
    with db_cursor() as cur:
        if folder_id is not None:
            exists = cur.execute("SELECT id FROM folders WHERE id = ?", (folder_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Folder not found")

        from app.storage import sync_storage_state
        sync_storage_state(cur)

        folder_rows = cur.execute(
            "SELECT id, name, parent_id, created_at FROM folders WHERE parent_id IS ? ORDER BY name COLLATE NOCASE",
            (folder_id,),
        ).fetchall()
        file_rows = cur.execute(
            "SELECT id, name, folder_id, size_bytes, mime_type, created_at FROM files "
            "WHERE folder_id IS ? ORDER BY name COLLATE NOCASE",
            (folder_id,),
        ).fetchall()
        breadcrumb = _build_breadcrumb(cur, folder_id)

        return BrowseResponse(
            folders=[FolderOut(**dict(r)) for r in folder_rows],
            files=[FileOut(**dict(r)) for r in file_rows],
            breadcrumb=[FolderOut(**b) for b in breadcrumb],
        )


@router.delete("/{folder_id}")
def delete_folder(folder_id: int, user: str = Depends(get_current_user)):
    from app.storage import delete_files_under_folder

    with db_cursor() as cur:
        row = cur.execute("SELECT id FROM folders WHERE id = ?", (folder_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Folder not found")

        # Remove the physical files inside this folder tree before the DB
        # cascade wipes their rows (otherwise we'd lose the storage_name).
        delete_files_under_folder(cur, folder_id)

        cur.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    return {"detail": "Folder deleted"}

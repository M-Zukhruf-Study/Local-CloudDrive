from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None


class FolderOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    created_at: str


class FileOut(BaseModel):
    id: int
    name: str
    folder_id: Optional[int]
    size_bytes: int
    mime_type: Optional[str]
    created_at: str


class BrowseResponse(BaseModel):
    folders: list[FolderOut]
    files: list[FileOut]
    breadcrumb: list[FolderOut]


class QuotaResponse(BaseModel):
    used_bytes: int
    quota_bytes: int
    used_gb: float
    quota_gb: float
    percent_used: float


class InitUploadRequest(BaseModel):
    file_name: str
    folder_id: Optional[int] = None
    total_size: int
    chunk_size: int
    mime_type: Optional[str] = None


class InitUploadResponse(BaseModel):
    session_id: str
    total_chunks: int
    uploaded_chunks: list[int]  # already-received indices, for resume


class ChunkStatusResponse(BaseModel):
    session_id: str
    uploaded_chunks: list[int]
    total_chunks: int
    status: str


class CompleteUploadResponse(BaseModel):
    file: FileOut

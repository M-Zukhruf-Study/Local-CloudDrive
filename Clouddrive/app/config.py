"""
Centralised configuration. Reads from .env (or real environment variables
in Docker) so nothing is hard-coded.
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    admin_username: str = "Admin"
    admin_password: str = "Family67"

    host: str = "0.0.0.0"
    port: int = 3167

    jwt_secret: str = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef"
    jwt_expire_hours: int = 24
    jwt_algorithm: str = "HS256"

    storage_quota_gb: int = 500
    storage_path: str = "./data/storage"
    temp_chunk_path: str = "./data/temp_chunks"
    db_path: str = "./data/db/clouddrive.db"

    chunk_size_bytes: int = 8 * 1024 * 1024  # 8MB

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def storage_quota_bytes(self) -> int:
        return self.storage_quota_gb * 1024 * 1024 * 1024


settings = Settings()

# Make sure the folders we need actually exist at startup.
Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
Path(settings.temp_chunk_path).mkdir(parents=True, exist_ok=True)
Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

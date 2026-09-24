from __future__ import annotations
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / '.env', env_file_encoding='utf-8', extra='ignore', case_sensitive=False)
    mongodb_uri: SecretStr = Field(description='MongoDB Atlas connection string.')
    mongodb_db: str = Field(default='balancesheet', description='Database name.')
    mongodb_timeout_ms: int = Field(default=5000, ge=100)
    allowed_origins: list[str] = Field(default=['http://localhost:5173', 'http://127.0.0.1:5173'], description='CORS origins permitted to call the API.')
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    allowed_extensions: list[str] = Field(default=['.pdf', '.xlsx'])
    equation_tolerance_abs: Decimal = Field(default=Decimal('1'), ge=Decimal('0'))
    equation_tolerance_rel: Decimal = Field(default=Decimal('0.005'), ge=Decimal('0'))
    ocr_enabled: bool = Field(default=True, description='Turn OCR off to refuse scanned documents outright rather than attempting to read them.')
    ocr_language: str = Field(default='eng', description='Tesseract language code.')
    ocr_dpi: int = Field(default=300, ge=72, le=600)
    ocr_min_chars_per_page: int = Field(default=20, ge=0)
    ollama_host: str = Field(default='http://localhost:11434', description='Where Ollama is listening.')
    ollama_model: str = Field(default='qwen3:8b', description='The pulled model used to normalize terminology (Module 2).')
    ollama_timeout_s: float = Field(default=120.0, gt=0)
    ollama_num_ctx: int = Field(default=4096, ge=512)
    llm_required: bool = Field(default=False)
    normalization_confidence_floor: float = Field(default=0.5, ge=0, le=1)
    embedding_model: str = Field(default='nomic-embed-text', description='The pulled model used to embed text for retrieval (Module 4).')
    embedding_dim: int = Field(default=768, gt=0)
    embedding_timeout_s: float = Field(default=60.0, gt=0)
    storage_backend: str = Field(default='local')
    storage_dir: Path = Field(default=BACKEND_DIR / 'var' / 'uploads')
    max_prelim_inline_bytes: int = Field(default=8 * 1024 * 1024, ge=1)

    @field_validator('allowed_origins', 'allowed_extensions', mode='before')
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith('['):
                return value
            return [part.strip() for part in stripped.split(',') if part.strip()]
        return value

    @field_validator('allowed_extensions')
    @classmethod
    def _normalise_extensions(cls, value: list[str]) -> list[str]:
        return [ext if ext.startswith('.') else f'.{ext}' for ext in (e.lower() for e in value)]

    @field_validator('storage_dir')
    @classmethod
    def _resolve_storage_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

@lru_cache
def get_settings() -> Settings:
    return Settings()

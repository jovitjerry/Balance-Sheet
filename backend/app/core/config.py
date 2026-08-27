"""Application configuration.

All settings come from the repository-root ``.env`` file. Nothing is
hard-coded, and secrets never appear in source. See ``.env.example`` for the
full list of keys.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo root
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration, loaded from the repository-root ``.env``."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- MongoDB ----
    # SecretStr, not str: an Atlas SRV URI embeds the database password. A plain
    # str prints in full wherever a Settings object is repr'd - pytest's local
    # variable dumps on a failure, an exception handler, a debug log - which
    # writes the credential into places nobody thinks of as secret-bearing.
    # SecretStr renders as '**********' and only yields the value to an explicit
    # .get_secret_value() call.
    mongodb_uri: SecretStr = Field(description="MongoDB Atlas connection string.")
    mongodb_db: str = Field(default="balancesheet", description="Database name.")
    # Keep this short: the default 30s means an unreachable cluster hangs the
    # health check and the test suite instead of failing promptly.
    mongodb_timeout_ms: int = Field(default=5000, ge=100)

    # ---- API ----
    allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="CORS origins permitted to call the API.",
    )

    # ---- Uploads ----
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    # .xlsx only. The legacy .xls binary format is out of scope: openpyxl cannot
    # read it, and supporting it would mean a second parser for a format Excel
    # itself has not written by default since 2007.
    allowed_extensions: list[str] = Field(default=[".pdf", ".xlsx"])

    # ---- Accounting equation ----
    # Effective threshold is max(ABS, REL * |total_assets|). Published balance
    # sheets are rounded, so a fixed absolute tolerance is either too tight for
    # a large company or meaninglessly loose for a small one.
    equation_tolerance_abs: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    equation_tolerance_rel: Decimal = Field(default=Decimal("0.005"), ge=Decimal("0"))

    # ---- OCR ----
    ocr_enabled: bool = Field(
        default=True,
        description="Turn OCR off to refuse scanned documents outright rather "
        "than attempting to read them.",
    )
    ocr_language: str = Field(default="eng", description="Tesseract language code.")
    # 300 dpi is the accuracy floor Tesseract's own documentation recommends;
    # below it, digit confusion (5/6, 1/7) climbs sharply, and a misread digit
    # in a Balance Sheet is worse than a slow one.
    ocr_dpi: int = Field(default=300, ge=72, le=600)
    # A PDF page with fewer extractable characters than this is treated as
    # scanned. Judged per page, not per document: mixed filings - a digital
    # statement with a scanned signed page - are ordinary.
    ocr_min_chars_per_page: int = Field(default=20, ge=0)

    # ---- Module 2: local LLM via Ollama ----
    ollama_host: str = Field(
        default="http://localhost:11434", description="Where Ollama is listening."
    )
    # Selected 2026-08-26 by measurement, not reputation: 97% accuracy over 75
    # labelled cases, clean schema-constrained output with no chain-of-thought
    # leakage, 4.15s warm per label, and 6.4 GB on an 8 GB card. The
    # finance-tuned candidate did not beat it and answered every ambiguous and
    # most nonsense labels. Evidence and limitations:
    # backend/benchmarks/results/MODEL_SELECTION.md
    #
    # Still a setting, deliberately. Module 4 will drive the same provider with
    # different prompts and must choose its own model on its own evidence -
    # this benchmark measured terminology mapping and nothing else.
    ollama_model: str = Field(
        default="qwen3:8b",
        description="The pulled model used to normalize terminology (Module 2). "
        "Selected by the benchmark in backend/benchmarks; see "
        "results/MODEL_SELECTION.md.",
    )
    ollama_timeout_s: float = Field(default=120.0, gt=0)
    # The KV cache grows with the context window, and 8 GB of VRAM is the
    # binding constraint on this class of hardware. One label at a time needs
    # nothing like a long context.
    ollama_num_ctx: int = Field(default=4096, ge=512)
    # Default false: extraction is deterministic and complete without a model,
    # so an unreachable Ollama marks the terminology step needs_review rather
    # than throwing away a good extraction. Set true in CI or for a demo, where
    # a silently un-normalized document would be a false green.
    llm_required: bool = Field(default=False)
    # A policy floor, NOT a truth threshold. A model's stated confidence is not
    # a calibrated probability; it may demote a mapping to review and may never
    # rescue one that failed validation.
    normalization_confidence_floor: float = Field(default=0.5, ge=0, le=1)

    # ---- Module 4: retrieval embeddings ----
    # A DIFFERENT model from the one above, and deliberately its own setting.
    # Embedding and generation are different jobs on different schedules -
    # embed once per document, generate once per question - and choosing a chat
    # model must not silently choose a retriever too.
    #
    # nomic-embed-text is the starting default, chosen on hardware fit rather
    # than measurement: qwen3:8b occupies 6,460 MB of an 8 GB card, and at
    # 274 MB this is the strongest general-purpose embedder that comfortably
    # sits beside it. Unlike OLLAMA_MODEL this has NOT been benchmarked - there
    # is no labelled retrieval set yet - so it is a default, not a selection.
    # all-minilm (384 dim, 46 MB) is the fallback if VRAM becomes binding.
    embedding_model: str = Field(
        default="nomic-embed-text",
        description="The pulled model used to embed text for retrieval (Module 4).",
    )
    # Must match the model. A mismatch is caught at embed time with a message
    # naming both, rather than surfacing later as an opaque index rejection.
    embedding_dim: int = Field(default=768, gt=0)
    embedding_timeout_s: float = Field(default=60.0, gt=0)

    # ---- File storage ----
    storage_backend: str = Field(default="local")
    storage_dir: Path = Field(default=BACKEND_DIR / "var" / "uploads")

    # ---- Preliminary extraction ----
    # MongoDB caps a document at 16 MB; OCR text plus tables from a large
    # scanned PDF can approach that, so oversized payloads spill to storage.
    max_prelim_inline_bytes: int = Field(default=8 * 1024 * 1024, ge=1)

    @field_validator("allowed_origins", "allowed_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept comma-separated strings from ``.env`` as well as lists.

        Pydantic-settings would otherwise try to JSON-decode a plain string for
        a ``list`` field, which fails on ``a,b`` and produces a confusing error.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):  # leave real JSON to pydantic
                return value
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value

    @field_validator("allowed_extensions")
    @classmethod
    def _normalise_extensions(cls, value: list[str]) -> list[str]:
        return [ext if ext.startswith(".") else f".{ext}" for ext in (e.lower() for e in value)]

    @field_validator("storage_dir")
    @classmethod
    def _resolve_storage_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Cached so the ``.env`` file is read once per process, and so tests can
    clear it via ``get_settings.cache_clear()``.
    """
    return Settings()  # type: ignore[call-arg]  # values come from .env

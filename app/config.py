from pathlib import Path
from typing import Literal

from typing_extensions import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGAL_WORKFLOW_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    chroma_subdir: str = "chroma"
    sqlite_filename: str = "workflow.db"

    # deployment
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    """When set, POST/GET data routes require X-API-Key or Authorization: Bearer."""
    api_key: str | None = None
    max_upload_bytes: int = 40 * 1024 * 1024
    max_pdf_pages: int = 500
    """0 disables in-process per-IP sliding window limit."""
    rate_limit_requests_per_minute: int = 120

    # Embedding model (local, sentence-transformers)
    embedding_model: str = "all-MiniLM-L6-v2"

    # OCR: minimum chars per page before trying OCR
    ocr_char_threshold: int = 40

    # Chunking
    chunk_size: int = 900
    chunk_overlap: int = 120

    # Retrieval
    retrieval_top_k_dense: int = 20
    retrieval_top_k_bm25: int = 20
    retrieval_fusion_top_n: int = 12

    # Optional Gemini (Google AI Studio API key) for higher-quality drafts (still evidence-bound)
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_max_retries: int = 4

    @model_validator(mode="after")
    def _google_api_key_from_env(self) -> Self:
        import os

        if self.google_api_key is None:
            for key in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY"):
                val = os.environ.get(key)
                if val:
                    object.__setattr__(self, "google_api_key", val)
                    break
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sqlite_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / self.sqlite_filename

    @property
    def chroma_path(self) -> Path:
        p = self.data_dir / self.chroma_subdir
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()

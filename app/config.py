from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGAL_WORKFLOW_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    chroma_subdir: str = "chroma"
    sqlite_filename: str = "workflow.db"

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

    # Optional OpenAI for higher-quality drafts (still evidence-bound)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    @model_validator(mode="after")
    def _openai_from_std_env(self) -> Self:
        import os

        if self.openai_api_key is None and os.environ.get("OPENAI_API_KEY"):
            object.__setattr__(self, "openai_api_key", os.environ["OPENAI_API_KEY"])
        return self

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

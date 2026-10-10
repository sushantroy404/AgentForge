"""Settings. Relative paths resolve against the repo root, not the working directory."""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    APP_ENV: str = "development"
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173"
    DEMO_MODE: Literal["off", "replay", "auto"] = "off"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    ARCHITECT_MODEL: str = "gemma4:12b"
    SPECIALIST_MODEL: str = "gemma4:12b"
    EMBEDDING_MODEL: str = "bge-m3"
    OLLAMA_NUM_CTX: int = 4096
    OLLAMA_TIMEOUT_SECONDS: float = 120
    OLLAMA_KEEP_ALIVE: str = "30m"
    LLM_ENVELOPE_RETRIES: int = 1

    DATA_DIR: str = "./data"
    UPLOAD_DIR: str = "./data/uploads"
    LANCEDB_URI: str = "./data/lancedb"
    MANIFESTS_DIR: str = "./data/manifests"
    MAX_UPLOAD_MB: int = 5

    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 100
    RAG_TOP_K: int = 3

    # Calibrated thresholds for bge-m3 (overall and per-language)
    RAG_SCORE_THRESHOLD: float = 0.50
    RAG_SCORE_THRESHOLD_EN: float | None = 0.52
    RAG_SCORE_THRESHOLD_NE: float | None = 0.53
    RAG_SCORE_THRESHOLD_NE_ROMAN: float | None = 0.45

    SCOPE_OUT_MIN: float = 0.35
    SCOPE_OUT_MIN_EN: float | None = 0.50
    SCOPE_OUT_MIN_NE: float | None = 0.35
    SCOPE_OUT_MIN_NE_ROMAN: float | None = 0.39

    SCOPE_MARGIN: float = 0.03
    SCOPE_MARGIN_EN: float | None = 0.06
    SCOPE_MARGIN_NE: float | None = 0.03
    SCOPE_MARGIN_NE_ROMAN: float | None = 0.03

    MAX_REPAIR_ATTEMPTS: int = 2
    SPECIALIST_MAX_TOOL_CALLS: int = 2

    # Query rewriting for Roman Nepali (on | off)
    QUERY_REWRITE: str = "on"

    # Memory reduction settings (low VRAM profile)
    MAX_HISTORY_TURNS: int = 3
    ARCHITECT_HISTORY_TURNS: int | None = None
    SPECIALIST_HISTORY_TURNS: int | None = None
    RAG_MAX_CHUNK_CHARS: int = 400

    # Language detection
    LANG_DETECT_LLM_FALLBACK: str = "off"

    def get_rag_score_threshold(self, lang: str | None = None) -> float:
        if self.DEMO_MODE == "replay" or self.RAG_SCORE_THRESHOLD < 0.2:
            return self.RAG_SCORE_THRESHOLD
        if lang == "ne" and self.RAG_SCORE_THRESHOLD_NE is not None:
            return self.RAG_SCORE_THRESHOLD_NE
        if lang == "ne_roman" and self.RAG_SCORE_THRESHOLD_NE_ROMAN is not None:
            return self.RAG_SCORE_THRESHOLD_NE_ROMAN
        if lang == "en" and self.RAG_SCORE_THRESHOLD_EN is not None:
            return self.RAG_SCORE_THRESHOLD_EN
        return self.RAG_SCORE_THRESHOLD

    def get_scope_out_min(self, lang: str | None = None) -> float:
        if self.DEMO_MODE == "replay" or self.RAG_SCORE_THRESHOLD < 0.2:
            return self.SCOPE_OUT_MIN
        if lang == "ne" and self.SCOPE_OUT_MIN_NE is not None:
            return self.SCOPE_OUT_MIN_NE
        if lang == "ne_roman" and self.SCOPE_OUT_MIN_NE_ROMAN is not None:
            return self.SCOPE_OUT_MIN_NE_ROMAN
        if lang == "en" and self.SCOPE_OUT_MIN_EN is not None:
            return self.SCOPE_OUT_MIN_EN
        return self.SCOPE_OUT_MIN

    def get_scope_margin(self, lang: str | None = None) -> float:
        if self.DEMO_MODE == "replay" or self.RAG_SCORE_THRESHOLD < 0.2:
            return self.SCOPE_MARGIN
        if lang == "ne" and self.SCOPE_MARGIN_NE is not None:
            return self.SCOPE_MARGIN_NE
        if lang == "ne_roman" and self.SCOPE_MARGIN_NE_ROMAN is not None:
            return self.SCOPE_MARGIN_NE_ROMAN
        if lang == "en" and self.SCOPE_MARGIN_EN is not None:
            return self.SCOPE_MARGIN_EN
        return self.SCOPE_MARGIN

    @staticmethod
    def resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (ROOT / path).resolve()

    @property
    def data_dir(self) -> Path: return self.resolve(self.DATA_DIR)
    @property
    def upload_dir(self) -> Path: return self.resolve(self.UPLOAD_DIR)
    @property
    def lancedb_uri(self) -> Path: return self.resolve(self.LANCEDB_URI)
    @property
    def manifests_dir(self) -> Path: return self.resolve(self.MANIFESTS_DIR)
    @property
    def demo_dir(self) -> Path: return self.data_dir / "demo"
    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.lancedb_uri, self.manifests_dir, self.manifests_dir / "sessions"):
            d.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s

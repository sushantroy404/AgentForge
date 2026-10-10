"""Settings. Relative paths resolve against the repo root, not the working directory."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    APP_ENV: str = "development"
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    ARCHITECT_MODEL: str = "gemma4:e4b"
    SPECIALIST_MODEL: str = "gemma4:e4b"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_NUM_CTX: int = 8192
    OLLAMA_TIMEOUT_SECONDS: float = 60
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
    RAG_SCORE_THRESHOLD: float = 0.55
    SCOPE_OUT_MIN: float = 0.55
    SCOPE_MARGIN: float = 0.05
    MAX_REPAIR_ATTEMPTS: int = 2
    SPECIALIST_MAX_TOOL_CALLS: int = 2

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
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.lancedb_uri, self.manifests_dir, self.manifests_dir / "sessions"):
            d.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s

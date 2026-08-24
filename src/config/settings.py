from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LicitAll"
    debug: bool = False
    licitall_host: str = "0.0.0.0"
    licitall_port: int = 8000

    database_url: str = "postgresql+asyncpg://licitall:licitall@localhost:5432/licitall"
    redis_url: str = "redis://localhost:6379/0"

    raw_docs_dir: Path = Field(default=ROOT_DIR / "data" / "raw")

    pncp_consulta_base_url: str = "https://pncp.gov.br/api/consulta"
    pncp_core_base_url: str = "https://pncp.gov.br/api/pncp"
    pncp_timeout_seconds: float = 60.0
    pncp_page_size: int = 50

    minha_receita_base_url: str = "http://localhost:8001"

    evolution_api_url: str = "http://localhost:8080"
    evolution_api_key: str = "licitall-dev-evolution-key"
    evolution_instance: str = "licitall"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def raw_docs_path(self) -> Path:
        path = self.raw_docs_dir
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()

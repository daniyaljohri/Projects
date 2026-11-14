import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIALECTS = ("tsql", "sqlite")
MAX_SQL_RETRIES = 3
SCHEMA_RETRIEVAL_METHODS = ("off", "keyword", "embedding", "hybrid")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model: str
    pack: str
    db_dialect: str
    db_connection: str
    # how many times a query that failed to parse or run is sent back to Claude to fix
    sql_retries: int = 1
    # off sends every table; the others send only the top_k tables most relevant to the question
    schema_retrieval: str = "off"
    schema_top_k: int = 3
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    @property
    def pack_dir(self) -> Path:
        return PROJECT_ROOT / "packs" / self.pack


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. Add it to .env (see .env.example).")
    return value


@lru_cache
def get_settings(require_pack: bool = True) -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    dialect = _required("ASKIT_DB_DIALECT").lower()
    if dialect not in DIALECTS:
        raise ConfigError(f"ASKIT_DB_DIALECT must be one of {', '.join(DIALECTS)}, not '{dialect}'.")

    connection = _required("ASKIT_DB_CONNECTION")
    if dialect == "sqlite" and not Path(connection).is_absolute():
        connection = str(PROJECT_ROOT / connection)

    retries = os.getenv("ASKIT_SQL_RETRIES", "1").strip() or "1"
    if not retries.isdigit() or int(retries) > MAX_SQL_RETRIES:
        raise ConfigError(f"ASKIT_SQL_RETRIES must be a whole number from 0 to {MAX_SQL_RETRIES}, not '{retries}'.")

    retrieval = os.getenv("ASKIT_SCHEMA_RETRIEVAL", "off").strip().lower() or "off"
    if retrieval not in SCHEMA_RETRIEVAL_METHODS:
        raise ConfigError(f"ASKIT_SCHEMA_RETRIEVAL must be one of {', '.join(SCHEMA_RETRIEVAL_METHODS)}, not '{retrieval}'.")
    top_k = os.getenv("ASKIT_SCHEMA_TOP_K", "3").strip() or "3"
    if not top_k.isdigit() or int(top_k) < 1:
        raise ConfigError(f"ASKIT_SCHEMA_TOP_K must be a whole number of tables, at least 1, not '{top_k}'.")

    settings = Settings(
        # checked when Claude is first called, so database-only commands work without a key
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        model=_required("ASKIT_MODEL"),
        pack=_required("ASKIT_PACK"),
        db_dialect=dialect,
        db_connection=connection,
        sql_retries=int(retries),
        schema_retrieval=retrieval,
        schema_top_k=int(top_k),
        embedding_model=os.getenv("ASKIT_EMBEDDING_MODEL", "").strip() or "BAAI/bge-small-en-v1.5",
    )

    if require_pack and not settings.pack_dir.is_dir():
        raise ConfigError(f"Data pack '{settings.pack}' not found at {settings.pack_dir}.")

    return settings

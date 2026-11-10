import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIALECTS = ("tsql", "sqlite")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model: str
    pack: str
    db_dialect: str
    db_connection: str

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

    settings = Settings(
        # checked when Claude is first called, so database-only commands work without a key
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        model=_required("ASKIT_MODEL"),
        pack=_required("ASKIT_PACK"),
        db_dialect=dialect,
        db_connection=connection,
    )

    if require_pack and not settings.pack_dir.is_dir():
        raise ConfigError(f"Data pack '{settings.pack}' not found at {settings.pack_dir}.")

    return settings

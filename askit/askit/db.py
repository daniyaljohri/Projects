import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from askit.config import Settings

LOGIN_TIMEOUT_SECONDS = 10
QUERY_TIMEOUT_SECONDS = 30
MAX_ROWS = 5000


class DatabaseError(Exception):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict]
    truncated: bool

    @property
    def row_count(self) -> int:
        return len(self.rows)


class Database:
    def __init__(self, dialect: str, connection: str, schemas: tuple[str, ...] = ()):
        self.dialect = dialect
        self.connection = connection
        # SQLite has no schemas; the file is attached under each schema name so chatbot.v_orders_full still resolves
        self.schemas = schemas

    @classmethod
    def from_settings(cls, settings: Settings, schemas: tuple[str, ...] = ()) -> "Database":
        return cls(settings.db_dialect, settings.db_connection, schemas)

    def describe(self) -> str:
        if self.dialect == "sqlite":
            return f"SQLite file {self.connection}"
        parts = dict(
            part.split("=", 1) for part in self.connection.split(";") if "=" in part
        )
        parts = {key.strip().upper(): value for key, value in parts.items()}
        return f"SQL Server {parts.get('SERVER', '?')}, database {parts.get('DATABASE', '?')}, user {parts.get('UID', 'Windows login')}"

    def _driver_errors(self) -> tuple[type[Exception], ...]:
        if self.dialect == "sqlite":
            return (sqlite3.Error,)
        import pyodbc
        return (pyodbc.Error,)

    def _connect(self, timeout: int):
        if self.dialect == "sqlite":
            path = Path(self.connection)
            if not path.exists():
                raise DatabaseError(f"SQLite file not found: {path}")
            # mode=ro: the file itself refuses writes, the SQLite version of a read-only login
            uri = f"file:{path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            for schema in self.schemas:
                conn.execute(f'ATTACH DATABASE ? AS "{schema}"', (uri,))
            deadline = time.monotonic() + timeout
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
            return conn

        # imported here so SQLite users don't need ODBC installed
        import pyodbc

        conn = pyodbc.connect(self.connection, autocommit=True, timeout=LOGIN_TIMEOUT_SECONDS)
        conn.timeout = timeout
        cursor = conn.cursor()
        # SSMS runs with ARITHABORT ON and ODBC does not; without it the same query can get a much slower plan
        cursor.execute("SET ARITHABORT ON")
        cursor.close()
        return conn

    def run(self, sql: str, max_rows: int = MAX_ROWS, timeout: int = QUERY_TIMEOUT_SECONDS) -> QueryResult:
        driver_errors = self._driver_errors()
        try:
            conn = self._connect(timeout)
        except driver_errors as error:
            raise DatabaseError(f"Could not connect to {self.describe()}: {error}") from error

        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            if cursor.description is None:
                return QueryResult(columns=[], rows=[], truncated=False)
            columns = [column[0] for column in cursor.description]
            fetched = cursor.fetchmany(max_rows + 1)
            rows = [dict(zip(columns, row)) for row in fetched[:max_rows]]
            return QueryResult(columns=columns, rows=rows, truncated=len(fetched) > max_rows)
        except driver_errors as error:
            raise DatabaseError(_clean_error(error)) from error
        finally:
            conn.close()

    def list_tables(self) -> list[str]:
        if self.dialect == "sqlite":
            sql = "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
        else:
            sql = (
                "SELECT TABLE_SCHEMA + '.' + TABLE_NAME AS name "
                "FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        return [row["name"] for row in self.run(sql).rows]


def _clean_error(error: Exception) -> str:
    # pyodbc puts the message last, wrapped in driver tags like [Microsoft][ODBC Driver 17 for SQL Server]
    message = str(error.args[-1]) if error.args else str(error)
    message = re.sub(r"\[[^\]]*\]|\(SQL\w+W\)", "", message)
    return " ".join(message.split())

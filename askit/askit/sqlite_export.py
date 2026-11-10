import sqlite3
import time
from datetime import date, datetime, time as clock
from decimal import Decimal
from pathlib import Path

from askit.db import Database
from askit.introspect import PROFILE_TIMEOUT_SECONDS
from askit.pack import Pack

BATCH_SIZE = 5000


def _sqlite_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (date, clock)):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def _sqlite_type(type_code, sample) -> str:
    kind = type_code if isinstance(type_code, type) else type(sample)
    if kind is bool or (isinstance(kind, type) and issubclass(kind, int)):
        return "INTEGER"
    if kind in (float, Decimal):
        return "REAL"
    if kind in (bytes, bytearray):
        return "BLOB"
    return "TEXT"


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def export_table(source: Database, table: str, target: sqlite3.Connection, target_table: str) -> int:
    conn = source._connect(PROFILE_TIMEOUT_SECONDS)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        columns = [c[0] for c in cursor.description]
        type_codes = [c[1] for c in cursor.description]
        first = cursor.fetchmany(BATCH_SIZE)

        samples = [next((row[i] for row in first if row[i] is not None), None) for i in range(len(columns))]
        definitions = ", ".join(f"{_quote(c)} {_sqlite_type(t, s)}" for c, t, s in zip(columns, type_codes, samples))
        target.execute(f"CREATE TABLE {_quote(target_table)} ({definitions})")

        insert = f"INSERT INTO {_quote(target_table)} VALUES ({', '.join('?' for _ in columns)})"
        copied = 0
        batch = first
        while batch:
            target.executemany(insert, [tuple(_sqlite_value(v) for v in row) for row in batch])
            copied += len(batch)
            batch = cursor.fetchmany(BATCH_SIZE)
        return copied
    finally:
        conn.close()


def export_pack(source: Database, pack: Pack, out_path: Path, log=print) -> dict[str, int]:
    """Copy every table in the pack into one SQLite file, named without the schema."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    partial = out_path.with_suffix(".partial")
    partial.unlink(missing_ok=True)

    counts = {}
    target = sqlite3.connect(partial)
    try:
        for table in pack.tables:
            started = time.perf_counter()
            local_name = table.name.split(".")[-1]
            counts[local_name] = export_table(source, table.name, target, local_name)
            target.commit()
            log(f"Copied {table.name} -> {local_name}: {counts[local_name]:,} rows, {time.perf_counter() - started:.1f}s")
        target.execute("ANALYZE")
        target.commit()
    finally:
        target.close()

    # only replace an existing file once the whole copy has succeeded
    partial.replace(out_path)
    return counts

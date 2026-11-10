from dataclasses import dataclass, field

from askit.db import Database

PROFILE_TIMEOUT_SECONDS = 300
TOP_VALUES_LIMIT = 25
LOW_CARDINALITY = 25

NUMERIC_TYPES = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "money", "smallmoney", "integer", "double")
DATE_TYPES = ("date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "time", "timestamp")
# types that can't be grouped or compared cheaply, so they are listed but not profiled
SKIP_TYPES = {
    "tsql": ("text", "ntext", "image", "xml", "varbinary", "binary", "geography", "geometry", "hierarchyid", "sql_variant"),
    "sqlite": ("blob",),
}


@dataclass
class ColumnProfile:
    name: str
    data_type: str
    dialect: str = "tsql"
    null_pct: float | None = None
    distinct: int | None = None
    min: object = None
    max: object = None
    top_values: list = field(default_factory=list)

    @property
    def kind(self) -> str:
        base = self.data_type.lower().split("(")[0].strip()
        if base in NUMERIC_TYPES or base == "bit":
            return "number"
        if base in DATE_TYPES:
            return "date"
        if base in SKIP_TYPES[self.dialect]:
            return "skip"
        return "text"


@dataclass
class TableProfile:
    name: str
    row_count: int
    columns: list[ColumnProfile]


def _quote(db: Database, name: str) -> str:
    if db.dialect == "sqlite":
        return '"' + name.replace('"', '""') + '"'
    return "[" + name.replace("]", "]]") + "]"


def _table_ref(db: Database, table: str) -> str:
    return ".".join(_quote(db, part) for part in table.split("."))


def list_columns(db: Database, schemas: list[str] | None = None) -> dict[str, list[tuple[str, str]]]:
    """Tables and views the login can see, with their columns in order."""
    tables: dict[str, list[tuple[str, str]]] = {}
    if db.dialect == "sqlite":
        names = db.run("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name").rows
        for row in names:
            info = db.run(f"PRAGMA table_info({_quote(db, row['name'])})").rows
            tables[row["name"]] = [(c["name"], c["type"] or "text") for c in info]
        return tables

    rows = db.run(
        "SELECT TABLE_SCHEMA AS s, TABLE_NAME AS t, COLUMN_NAME AS c, DATA_TYPE AS d "
        "FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION",
        max_rows=50_000,
    ).rows
    wanted = {s.lower() for s in schemas or []}
    for row in rows:
        if wanted and row["s"].lower() not in wanted:
            continue
        tables.setdefault(f"{row['s']}.{row['t']}", []).append((row["c"], row["d"]))
    return tables


def profile_table(db: Database, table: str, columns: list[tuple[str, str]]) -> TableProfile:
    profiles = [ColumnProfile(name, data_type, db.dialect) for name, data_type in columns]
    ref = _table_ref(db, table)

    parts = ["COUNT(*) AS row_count"]
    for i, column in enumerate(profiles):
        if column.kind == "skip":
            continue
        quoted = _quote(db, column.name)
        # SQL Server can't MIN/MAX a bit column
        value = f"CAST({quoted} AS INT)" if column.data_type.lower() == "bit" else quoted
        parts.append(f"COUNT({quoted}) AS n{i}")
        parts.append(f"COUNT(DISTINCT {quoted}) AS d{i}")
        if column.kind in ("number", "date"):
            parts += [f"MIN({value}) AS lo{i}", f"MAX({value}) AS hi{i}"]

    stats = db.run(f"SELECT {', '.join(parts)} FROM {ref}", timeout=PROFILE_TIMEOUT_SECONDS).rows[0]
    row_count = stats["row_count"]

    for i, column in enumerate(profiles):
        if column.kind == "skip":
            continue
        non_null = stats[f"n{i}"]
        column.null_pct = round(100 * (row_count - non_null) / row_count, 1) if row_count else 0.0
        column.distinct = stats[f"d{i}"]
        column.min = stats.get(f"lo{i}")
        column.max = stats.get(f"hi{i}")

        if column.kind in ("text", "number") and 0 < column.distinct <= LOW_CARDINALITY:
            quoted = _quote(db, column.name)
            top = f"TOP {TOP_VALUES_LIMIT} " if db.dialect == "tsql" else ""
            limit = "" if db.dialect == "tsql" else f" LIMIT {TOP_VALUES_LIMIT}"
            values = db.run(
                f"SELECT {top}{quoted} AS v, COUNT(*) AS n FROM {ref} WHERE {quoted} IS NOT NULL "
                f"GROUP BY {quoted} ORDER BY COUNT(*) DESC{limit}",
                timeout=PROFILE_TIMEOUT_SECONDS,
            ).rows
            column.top_values = [row["v"] for row in values]

    return TableProfile(table, row_count, profiles)


def describe_profile(profile: TableProfile) -> str:
    """Compact text version of a profile, used in the drafting prompt."""
    lines = [f"Table {profile.name}: {profile.row_count:,} rows"]
    for c in profile.columns:
        line = f"- {c.name} ({c.data_type})"
        if c.kind != "skip" and c.distinct is not None:
            line += f", {c.distinct:,} distinct, {c.null_pct}% null"
        if c.min is not None:
            line += f", range {c.min} to {c.max}"
        if c.top_values:
            line += f", values: {', '.join(str(v) for v in c.top_values)}"
        lines.append(line)
    return "\n".join(lines)

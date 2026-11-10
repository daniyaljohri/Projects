from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from askit.db import Database, DatabaseError
from askit.guardrails import GuardrailError, check_sql
from askit.introspect import TableProfile, describe_profile
from askit.llm import LLM, Usage
from askit.prompt import DIALECT_NOTES

DRAFT_MAX_TOKENS = 16000
EXAMPLE_TIMEOUT_SECONDS = 120
VALUES_LIMIT = 12

DRAFT_PROMPT = """You document a database so that an AI assistant can write correct SQL against it for business users.

You get the tables a read-only login can see, with a profile of every column: type, distinct count, null rate, range and the most common values.

Write:
- display_name and a one or two sentence description of what the data covers.
- currency, if amounts are in a known currency, otherwise an empty string.
- data_range: the earliest and latest date of the main business event (orders, transactions...), from the profiled ranges, as YYYY-MM-DD.
- For every table: its grain ("one row per ..."), a one to three sentence description of what it is for, and a short description of every column (meaning, unit, and whether higher is better when that isn't obvious). Use the exact table and column names given.
- rules: 4 to 10 short rules the SQL writer must know, based on what the profile shows (how values are stored, which column defines a metric, which table to prefer, traps like repeated rows).
- examples: 8 question and SQL pairs in {dialect_name} that a business user would ask, from simple counts to rankings and trends. Use only the given tables and columns.
- suggested_questions: 6 varied questions a business user could click to start exploring.

Only describe what the names and profile support. If a column's meaning is unclear, say so briefly instead of guessing.

SQL dialect notes:
{dialect_notes}"""

DRAFT_TOOL = {
    "name": "write_pack",
    "description": "Record the documentation for the database.",
    "input_schema": {
        "type": "object",
        "properties": {
            "display_name": {"type": "string"},
            "description": {"type": "string"},
            "currency": {"type": "string"},
            "data_range": {
                "type": "object",
                "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
            },
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "grain": {"type": "string"},
                        "description": {"type": "string"},
                        "columns": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
                                "required": ["name", "description"],
                            },
                        },
                    },
                    "required": ["name", "grain", "description", "columns"],
                },
            },
            "rules": {"type": "array", "items": {"type": "string"}},
            "examples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}, "sql": {"type": "string"}},
                    "required": ["question", "sql"],
                },
            },
            "suggested_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["display_name", "description", "tables", "rules", "examples", "suggested_questions"],
    },
}


@dataclass
class Draft:
    pack: dict
    semantic: dict
    examples: dict
    rejected_examples: list[tuple[str, str]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


def _show_values(column) -> bool:
    if not column.top_values or column.distinct is None:
        return False
    if column.kind == "text":
        return column.distinct <= VALUES_LIMIT
    # small sets of codes like 0/1 flags or 1-5 scores
    return column.kind == "number" and column.distinct <= 6


def draft_pack(name: str, profiles: list[TableProfile], db: Database, llm: LLM | None) -> Draft:
    written = {}
    usage = Usage()
    if llm:
        dialect_name, notes = DIALECT_NOTES[db.dialect]
        system = DRAFT_PROMPT.format(dialect_name=dialect_name, dialect_notes="\n".join(f"- {n}" for n in notes))
        message = "\n\n".join(describe_profile(p) for p in profiles)
        written = llm.call_tool(system, message, DRAFT_TOOL, usage, max_tokens=DRAFT_MAX_TOKENS)

    written_tables = {t["name"].lower(): t for t in written.get("tables", [])}
    tables = []
    for profile in profiles:
        doc = written_tables.get(profile.name.lower(), {})
        described = {c["name"].lower(): c["description"] for c in doc.get("columns", [])}
        columns = []
        # columns always come from the database, in its order; only descriptions come from the model
        for column in profile.columns:
            entry = {"name": column.name, "description": described.get(column.name.lower(), "")}
            if _show_values(column):
                entry["values"] = [_plain(v) for v in column.top_values]
            columns.append(entry)
        tables.append({
            "name": profile.name,
            "grain": doc.get("grain", ""),
            "description": doc.get("description", ""),
            "columns": columns,
        })

    allowed = {p.name.lower() for p in profiles}
    kept, rejected = [], []
    for example in written.get("examples", []):
        try:
            checked = check_sql(example["sql"], db.dialect, allowed)
            db.run(checked.sql, max_rows=5, timeout=EXAMPLE_TIMEOUT_SECONDS)
            kept.append({"question": example["question"], "sql": checked.sql.rstrip() + "\n"})
        except (GuardrailError, DatabaseError) as error:
            rejected.append((example["question"], str(error)))

    data_range = written.get("data_range") or {}
    pack = {
        "name": name,
        "display_name": written.get("display_name", name),
        "description": written.get("description", ""),
        "currency": written.get("currency", ""),
    }
    if data_range.get("from"):
        pack["data_range"] = {"from": data_range["from"], "to": data_range.get("to", "")}
    pack["suggested_questions"] = written.get("suggested_questions", [])

    return Draft(
        pack=pack,
        semantic={"tables": tables, "rules": written.get("rules", [])},
        examples={"dialect": db.dialect, "examples": kept},
        rejected_examples=rejected,
        usage=usage,
    )


def _plain(value):
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


class _Dumper(yaml.SafeDumper):
    pass


def _string(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _string)


def write_draft(draft: Draft, pack_dir: Path) -> list[Path]:
    pack_dir.mkdir(parents=True, exist_ok=True)
    header = f"# Drafted by askit init on {date.today().isoformat()}. Review every line before relying on it.\n"
    files = {"pack.yaml": draft.pack, "semantic.yaml": draft.semantic, "examples.yaml": draft.examples}
    written = []
    for filename, content in files.items():
        path = pack_dir / filename
        body = yaml.dump(content, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120)
        path.write_text(header + body, encoding="utf-8")
        written.append(path)
    return written

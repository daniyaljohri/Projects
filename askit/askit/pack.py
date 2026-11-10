from dataclasses import dataclass, field
from pathlib import Path

import yaml


class PackError(Exception):
    pass


@dataclass
class Column:
    name: str
    description: str = ""
    values: list = field(default_factory=list)


@dataclass
class Table:
    name: str
    grain: str
    description: str
    columns: list[Column]


@dataclass
class Example:
    question: str
    sql: str


@dataclass
class Pack:
    name: str
    display_name: str
    description: str
    currency: str
    data_from: str
    data_to: str
    tables: list[Table]
    rules: list[str]
    examples: list[Example]
    examples_dialect: str

    @property
    def allowed_tables(self) -> set[str]:
        return {table.name.lower() for table in self.tables}


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise PackError(f"Missing pack file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise PackError(f"{path.name} is not valid YAML: {error}") from error
    if not isinstance(data, dict):
        raise PackError(f"{path.name} should contain a mapping at the top level.")
    return data


def load_pack(pack_dir: Path) -> Pack:
    info = _read_yaml(pack_dir / "pack.yaml")
    semantic = _read_yaml(pack_dir / "semantic.yaml")
    examples = _read_yaml(pack_dir / "examples.yaml")

    tables = []
    for raw in semantic.get("tables") or []:
        if not raw.get("name") or not raw.get("columns"):
            raise PackError("Every table in semantic.yaml needs a name and columns.")
        columns = [
            Column(
                name=c["name"],
                description=str(c.get("description", "")).strip(),
                values=list(c.get("values") or []),
            )
            for c in raw["columns"]
        ]
        names = [c.name.lower() for c in columns]
        if len(names) != len(set(names)):
            raise PackError(f"{raw['name']} lists the same column twice.")
        tables.append(
            Table(
                name=raw["name"],
                grain=str(raw.get("grain", "")).strip(),
                description=" ".join(str(raw.get("description", "")).split()),
                columns=columns,
            )
        )
    if not tables:
        raise PackError("semantic.yaml does not list any tables.")

    data_range = info.get("data_range") or {}
    return Pack(
        name=info.get("name", pack_dir.name),
        display_name=info.get("display_name", pack_dir.name),
        description=" ".join(str(info.get("description", "")).split()),
        currency=info.get("currency", ""),
        data_from=str(data_range.get("from", "")),
        data_to=str(data_range.get("to", "")),
        tables=tables,
        rules=[str(rule) for rule in semantic.get("rules") or []],
        examples=[
            Example(question=e["question"], sql=e["sql"].strip())
            for e in examples.get("examples") or []
        ],
        examples_dialect=examples.get("dialect", "tsql"),
    )

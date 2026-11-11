from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

WRITE_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
)


class GuardrailError(Exception):
    pass


@dataclass
class CheckedQuery:
    sql: str
    tables: list[str]


def check_sql(sql: str, dialect: str, allowed_tables: set[str]) -> CheckedQuery:
    """Reject anything that is not one read-only SELECT over the allowed tables."""
    allowed = {name.lower() for name in allowed_tables}

    # SqlglotError covers parse errors and tokenizer errors, e.g. an unclosed quote around a name
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except SqlglotError as error:
        raise GuardrailError(f"The query could not be parsed: {_first_line(error)}") from error

    if not statements:
        raise GuardrailError("The query is empty.")
    if len(statements) > 1:
        raise GuardrailError("Only one statement is allowed.")

    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise GuardrailError(f"Only SELECT queries are allowed, not {tree.key.upper()}.")

    for node in tree.walk():
        if isinstance(node, WRITE_NODES):
            raise GuardrailError(f"{node.key.upper()} is not allowed.")
        if isinstance(node, exp.Select) and node.args.get("into"):
            raise GuardrailError("SELECT INTO is not allowed.")

    cte_names = {cte.alias.lower() for cte in tree.find_all(exp.CTE)}
    tables = []
    for table in tree.find_all(exp.Table):
        if table.catalog:
            raise GuardrailError(f"Cross-database or linked server references are not allowed: {table.sql(dialect)}.")
        # OPENROWSET, OPENQUERY and table functions parse as a table whose name is not a plain identifier
        if not isinstance(table.this, exp.Identifier):
            raise GuardrailError("Only named tables and views can be queried.")

        name = f"{table.db}.{table.name}".lower() if table.db else table.name.lower()
        if not table.db and name in cte_names:
            continue
        if name not in allowed:
            raise GuardrailError(f"{name} is not one of the tables Askit can query.")
        if name not in tables:
            tables.append(name)

    if not tables:
        raise GuardrailError("The query does not read from any allowed table.")

    return CheckedQuery(sql=sql.strip(), tables=tables)


def _first_line(error: Exception) -> str:
    return str(error).splitlines()[0]

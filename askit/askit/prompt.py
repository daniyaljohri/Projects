import sqlglot

from askit.pack import Pack, Table

DIALECT_NOTES = {
    "tsql": (
        "Microsoft SQL Server (T-SQL)",
        [
            "Limit rows with TOP n, never LIMIT.",
            "AVG of an integer column returns an integer in SQL Server; cast to FLOAT first.",
            "Integer division also truncates; multiply by 100.0 or cast before dividing.",
            "Use YEAR(), MONTH(), DATEADD(), DATEDIFF() and DATEFROMPARTS() for dates.",
            "ORDER BY is only allowed inside a subquery or CTE when it also uses TOP.",
        ],
    ),
    "sqlite": (
        "SQLite",
        [
            "Limit rows with LIMIT n.",
            "Dates are stored as text like '2017-11-24 10:15:00'; use strftime() and date().",
            "Integer division truncates; multiply by 1.0 before dividing.",
        ],
    ),
}


def _render_table(table: Table) -> str:
    lines = [f"### {table.name}", f"Grain: {table.grain}." if table.grain else "", table.description, "Columns:"]
    for column in table.columns:
        line = f"- {column.name}"
        if column.description:
            line += f": {column.description}"
        if column.values:
            line += f" (values: {', '.join(str(v) for v in column.values)})"
        lines.append(line)
    return "\n".join(line for line in lines if line)


def _example_sql(sql: str, source: str, target: str) -> str:
    if source == target:
        return sql
    return sqlglot.transpile(sql, read=source, write=target, pretty=True)[0]


def build_system_prompt(pack: Pack, dialect: str) -> str:
    dialect_name, notes = DIALECT_NOTES[dialect]

    sections = [
        f"You write {dialect_name} queries that answer business questions about {pack.display_name}.",
        "\n".join(
            part
            for part in [
                pack.description,
                f"Currency: {pack.currency}." if pack.currency else "",
                f"The data covers {pack.data_from} to {pack.data_to}." if pack.data_from else "",
            ]
            if part
        ),
        "## How to answer\n"
        "- Write one read-only SELECT query that answers the question, using only the tables and columns below.\n"
        "- If the question cannot be answered from these tables, or asks to change data, decline and say why in one sentence.\n"
        "- If the question is ambiguous, choose the most reasonable reading instead of asking.\n"
        "- Return the columns a reader needs to understand the answer, with clear names.",
        "## SQL dialect\n" + "\n".join(f"- {note}" for note in notes),
        "## Tables\n\n" + "\n\n".join(_render_table(table) for table in pack.tables),
    ]

    if pack.rules:
        sections.append("## Business rules\n" + "\n".join(f"- {rule}" for rule in pack.rules))

    if pack.examples:
        examples = [
            f"Question: {example.question}\nSQL:\n{_example_sql(example.sql, pack.examples_dialect, dialect)}"
            for example in pack.examples
        ]
        sections.append("## Examples\n\n" + "\n\n".join(examples))

    return "\n\n".join(sections)

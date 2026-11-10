import argparse
import sys

from askit.config import ConfigError, get_settings
from askit.db import Database, DatabaseError, QueryResult
from askit.guardrails import GuardrailError
from askit.llm import LLMError, format_value
from askit.pack import PackError, load_pack
from askit.pipeline import Answer, Askit
from askit.prompt import build_system_prompt

PREVIEW_ROWS = 10


def check(_args) -> int:
    settings = get_settings()
    db = Database.from_settings(settings)

    print(f"Pack:     {settings.pack}")
    print(f"Database: {db.describe()}")

    db.run("SELECT 1 AS ok")
    print("Connection: ok")

    tables = db.list_tables()
    print(f"Visible tables and views ({len(tables)}):")
    for name in tables:
        print(f"  {name}")
    return 0


def show_prompt(_args) -> int:
    settings = get_settings()
    pack = load_pack(settings.pack_dir)
    print(build_system_prompt(pack, settings.db_dialect))
    return 0


def print_table(result: QueryResult) -> None:
    rows = [[format_value(row[c], c) for c in result.columns] for row in result.rows[:PREVIEW_ROWS]]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(result.columns)]
    print("  ".join(c.ljust(w) for c, w in zip(result.columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))
    if result.row_count > PREVIEW_ROWS or result.truncated:
        more = "+" if result.truncated else ""
        print(f"... showing {len(rows)} of {result.row_count:,}{more} rows")


def print_answer(answer: Answer) -> None:
    print(f"\n{answer.text}\n")
    if answer.result and answer.result.rows:
        print_table(answer.result)
        print()
    if answer.sql:
        print(f"SQL:\n{answer.sql}\n")
    if answer.error:
        print(f"Error: {answer.error}\n")
    u = answer.usage
    print(f"[{answer.outcome} | {answer.seconds:.1f}s | {u.calls} calls | {u.input_tokens:,} in, {u.output_tokens:,} out, {u.cache_read_tokens:,} cached]")


def ask(args) -> int:
    askit = Askit(get_settings())
    print_answer(askit.ask(args.question))
    return 0


def chat(_args) -> int:
    askit = Askit(get_settings())
    history: list[Answer] = []
    print("Ask a question, or press Enter on an empty line to quit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        try:
            answer = askit.ask(question, history)
        except (DatabaseError, LLMError) as error:
            print(f"Error: {error}")
            continue
        print_answer(answer)
        history.append(answer)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="askit", description="Ask questions about a database in plain English.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("check", help="test the database connection and list what Askit can see").set_defaults(func=check)
    commands.add_parser("prompt", help="print the system prompt built from the data pack").set_defaults(func=show_prompt)

    ask_parser = commands.add_parser("ask", help="answer one question")
    ask_parser.add_argument("question")
    ask_parser.set_defaults(func=ask)

    commands.add_parser("chat", help="ask several questions, with follow-ups").set_defaults(func=chat)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, DatabaseError, PackError, LLMError, GuardrailError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

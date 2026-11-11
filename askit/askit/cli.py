import argparse
import dataclasses
import sys
import time

from askit.config import PROJECT_ROOT, ConfigError, get_settings
from askit.db import Database, DatabaseError, QueryResult
from askit.evaluate import EvalError, load_questions, result_path, run_eval, select_questions
from askit.guardrails import GuardrailError
from askit.introspect import list_columns, profile_table
from askit.llm import LLM, LLMError, format_value
from askit.onboard import draft_pack, write_draft
from askit.pack import PackError, load_pack
from askit.pipeline import Answer, Askit
from askit.prompt import build_system_prompt
from askit.sqlite_export import export_pack

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


def init(args) -> int:
    settings = get_settings(require_pack=False)
    pack_dir = PROJECT_ROOT / "packs" / args.pack
    if (pack_dir / "semantic.yaml").exists() and not args.force:
        print(f"Error: {pack_dir} already has a data pack. Use --force to overwrite it.", file=sys.stderr)
        return 1

    db = Database.from_settings(settings)
    print(f"Database: {db.describe()}")
    tables = list_columns(db, args.schema)
    if args.table:
        wanted = {t.lower() for t in args.table}
        tables = {name: cols for name, cols in tables.items() if name.lower() in wanted}
    if not tables:
        print("Error: no tables found. Check --schema and --table, and what the login can see.", file=sys.stderr)
        return 1

    profiles = []
    for name, columns in tables.items():
        started = time.perf_counter()
        print(f"Profiling {name} ({len(columns)} columns)...", end=" ", flush=True)
        profile = profile_table(db, name, columns)
        print(f"{profile.row_count:,} rows, {time.perf_counter() - started:.1f}s")
        profiles.append(profile)

    llm = None
    if not args.no_llm:
        model = args.model or settings.model
        print(f"Drafting descriptions, rules and examples with {model}...")
        llm = LLM(dataclasses.replace(settings, model=model))

    draft = draft_pack(args.pack, profiles, db, llm)
    for path in write_draft(draft, pack_dir):
        print(f"Wrote {path.relative_to(PROJECT_ROOT)}")

    examples = draft.examples["examples"]
    print(f"\n{len(profiles)} tables, {sum(len(p.columns) for p in profiles)} columns, {len(examples)} examples kept")
    for question, error in draft.rejected_examples:
        print(f"  dropped example: {question} ({error})")
    if llm:
        print(f"[{draft.usage.input_tokens:,} in, {draft.usage.output_tokens:,} out, {draft.usage.seconds:.1f}s]")
    print(f"\nNext: review the files in packs/{args.pack}, set ASKIT_PACK={args.pack} in .env, then run python -m askit prompt.")
    return 0


def export_sqlite(args) -> int:
    settings = get_settings()
    pack = load_pack(settings.pack_dir)
    out = args.out or f"data/{pack.name}.sqlite"
    out_path = PROJECT_ROOT / out
    if out_path.exists() and not args.force:
        print(f"Error: {out} already exists. Use --force to replace it.", file=sys.stderr)
        return 1

    source = Database.from_settings(settings, pack.schemas)
    print(f"Copying pack '{pack.name}' from {source.describe()} to {out}")
    counts = export_pack(source, pack, out_path)
    size_mb = out_path.stat().st_size / 1_048_576
    print(f"\nDone: {len(counts)} tables, {sum(counts.values()):,} rows, {size_mb:.1f} MB")
    print(f"To use it, set ASKIT_DB_DIALECT=sqlite and ASKIT_DB_CONNECTION={out}")
    return 0


def evaluate(args) -> int:
    settings = get_settings(require_pack=False)
    overrides = {key: value for key, value in (("pack", args.pack), ("model", args.model)) if value}
    if overrides:
        settings = dataclasses.replace(settings, **overrides)
    if not settings.pack_dir.is_dir():
        raise ConfigError(f"Data pack '{settings.pack}' not found at {settings.pack_dir}.")

    # questions come from the pack by default; --questions lets another pack (e.g. a drafted one) take the same test
    questions_file = PROJECT_ROOT / (args.questions or f"packs/{settings.pack}/eval/questions.yaml")
    reference_dialect, questions = load_questions(questions_file)
    questions = select_questions(questions, args.only, args.category, args.limit)

    askit = Askit(settings)
    out_path = result_path(settings.model, settings.pack, settings.db_dialect, args.tag)
    print(f"Pack: {settings.pack} | Model: {settings.model} | Database: {askit.db.describe()}")
    print(f"Questions: {len(questions)} from {questions_file.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"Writing {out_path.relative_to(PROJECT_ROOT).as_posix()}\n")

    records = run_eval(askit, questions, reference_dialect, out_path, args.tag,
                       questions_file.relative_to(PROJECT_ROOT).as_posix())

    outcomes = {}
    for record in records:
        outcomes[record["outcome"]] = outcomes.get(record["outcome"], 0) + 1
    tokens = {key: sum(r["usage"][key] for r in records) for key in ("input_tokens", "output_tokens", "cache_read_tokens")}
    reference_errors = [r["id"] for r in records if r["reference"] and r["reference"]["error"]]

    print("\nOutcomes: " + ", ".join(f"{name} {count}" for name, count in sorted(outcomes.items())))
    print(f"Tokens: {tokens['input_tokens']:,} in, {tokens['output_tokens']:,} out, {tokens['cache_read_tokens']:,} cached")
    print(f"Seconds: {sum(r['seconds'] for r in records):.1f} total")
    if reference_errors:
        print(f"Reference query errors (fix these first): {', '.join(reference_errors)}")
    return 0


def serve(args) -> int:
    import uvicorn

    get_settings()
    uvicorn.run("askit.api:app", host="127.0.0.1", port=args.port)
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

    init_parser = commands.add_parser("init", help="draft a data pack for the connected database")
    init_parser.add_argument("--pack", required=True, help="name of the new pack folder under packs/")
    init_parser.add_argument("--schema", action="append", help="only include this schema (repeatable, SQL Server)")
    init_parser.add_argument("--table", action="append", help="only include this table, e.g. chatbot.v_orders_full (repeatable)")
    init_parser.add_argument("--model", help="Claude model for drafting (defaults to ASKIT_MODEL)")
    init_parser.add_argument("--no-llm", action="store_true", help="profile only; leave descriptions for you to write")
    init_parser.add_argument("--force", action="store_true", help="overwrite an existing pack")
    init_parser.set_defaults(func=init)

    export_parser = commands.add_parser("export-sqlite", help="copy the pack's tables into a SQLite file")
    export_parser.add_argument("--out", help="output path relative to the project folder (default data/<pack>.sqlite)")
    export_parser.add_argument("--force", action="store_true", help="replace an existing file")
    export_parser.set_defaults(func=export_sqlite)

    eval_parser = commands.add_parser("eval", help="run the evaluation questions and save the results")
    eval_parser.add_argument("--pack", help="data pack to test (defaults to ASKIT_PACK)")
    eval_parser.add_argument("--model", help="Claude model (defaults to ASKIT_MODEL)")
    eval_parser.add_argument("--questions", help="question file relative to the project folder (default packs/<pack>/eval/questions.yaml)")
    eval_parser.add_argument("--tag", default="", help="label added to the result file name, e.g. baseline")
    eval_parser.add_argument("--only", nargs="+", metavar="ID", help="only these question ids")
    eval_parser.add_argument("--category", help="only this category")
    eval_parser.add_argument("--limit", type=int, help="only the first N questions, for cheap test runs")
    eval_parser.set_defaults(func=evaluate)

    serve_parser = commands.add_parser("serve", help="start the API for the web UI")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.set_defaults(func=serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, DatabaseError, PackError, LLMError, GuardrailError, EvalError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

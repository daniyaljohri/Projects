import argparse
import sys

from askit.config import ConfigError, get_settings
from askit.db import Database, DatabaseError
from askit.pack import PackError, load_pack
from askit.prompt import build_system_prompt


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="askit", description="Ask questions about a database in plain English.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("check", help="test the database connection and list what Askit can see").set_defaults(func=check)
    commands.add_parser("prompt", help="print the system prompt built from the data pack").set_defaults(func=show_prompt)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, DatabaseError, PackError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

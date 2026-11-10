import sqlite3

import pytest
import sqlglot

from askit.config import PROJECT_ROOT
from askit.db import Database, DatabaseError
from askit.guardrails import check_sql
from askit.pack import Column, Pack, Table, load_pack
from askit.sqlite_export import export_pack

OLIST = load_pack(PROJECT_ROOT / "packs" / "olist")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (order_id TEXT, amount REAL, items INTEGER, ordered_at TEXT)")
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", [(f"o{i}", i * 2.5, i % 3, f"2024-01-{i + 1:02d} 10:00:00") for i in range(12)])
    conn.execute("CREATE VIEW order_totals AS SELECT COUNT(*) AS orders, SUM(amount) AS revenue FROM orders")
    conn.commit()
    conn.close()
    return Database("sqlite", str(path), schemas=("chatbot",))


def small_pack():
    columns = [Column("order_id")]
    return Pack(
        name="shop", display_name="Shop", description="", currency="", data_from="", data_to="",
        tables=[Table("chatbot.orders", "", "", columns), Table("chatbot.order_totals", "", "", columns)],
        rules=[], examples=[], examples_dialect="tsql",
    )


def test_schema_names_resolve_in_sqlite(source):
    assert source.run("SELECT COUNT(*) AS n FROM chatbot.orders").rows == [{"n": 12}]
    assert source.run("SELECT COUNT(*) AS n FROM orders").rows == [{"n": 12}]
    with pytest.raises(DatabaseError, match="readonly"):
        source.run("DELETE FROM chatbot.orders")


def test_pack_schemas():
    assert OLIST.schemas == ("chatbot",)
    assert small_pack().schemas == ("chatbot",)


def test_export_copies_every_pack_table(source, tmp_path):
    out = tmp_path / "data" / "shop.sqlite"
    counts = export_pack(source, small_pack(), out, log=lambda _: None)

    assert counts == {"orders": 12, "order_totals": 1}
    assert not out.with_suffix(".partial").exists()

    copy = Database("sqlite", str(out), schemas=("chatbot",))
    assert copy.run("SELECT SUM(amount) AS total FROM chatbot.orders").rows == [{"total": 165.0}]
    assert copy.run("SELECT revenue FROM chatbot.order_totals").rows == [{"revenue": 165.0}]
    types = {r["name"]: r["type"] for r in copy.run("PRAGMA table_info(orders)").rows}
    assert types == {"order_id": "TEXT", "amount": "REAL", "items": "INTEGER", "ordered_at": "TEXT"}


def test_export_failure_keeps_the_old_file(source, tmp_path):
    out = tmp_path / "shop.sqlite"
    out.write_text("previous build")
    pack = small_pack()
    pack.tables.append(Table("chatbot.missing", "", "", [Column("x")]))

    with pytest.raises(sqlite3.Error):
        export_pack(source, pack, out, log=lambda _: None)
    assert out.read_text() == "previous build"


def empty_olist(tmp_path):
    """The five Olist views as empty SQLite tables, using the columns in semantic.yaml."""
    path = tmp_path / "olist.sqlite"
    conn = sqlite3.connect(path)
    for table in OLIST.tables:
        columns = ", ".join(f'"{c.name}"' for c in table.columns)
        conn.execute(f'CREATE TABLE "{table.name.split(".")[-1]}" ({columns})')
    conn.commit()
    conn.close()
    return Database("sqlite", str(path), schemas=OLIST.schemas)


@pytest.mark.parametrize("example", OLIST.examples, ids=lambda e: e.question[:40])
def test_olist_examples_run_on_sqlite(example, tmp_path):
    db = empty_olist(tmp_path)
    sql = sqlglot.transpile(example.sql, read="tsql", write="sqlite")[0]
    checked = check_sql(sql, "sqlite", OLIST.allowed_tables)
    db.run(checked.sql)

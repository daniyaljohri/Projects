import sqlite3

import pytest

from askit.db import Database
from askit.guardrails import check_sql
from askit.introspect import describe_profile, list_columns, profile_table
from askit.onboard import draft_pack, write_draft
from askit.pack import load_pack
from askit.prompt import build_system_prompt


@pytest.fixture
def shop_db(tmp_path):
    path = tmp_path / "shop.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (order_id TEXT, status TEXT, amount REAL, ordered_at TEXT, is_late INTEGER)")
    rows = [
        (f"o{i}", ["delivered", "delivered", "delivered", "canceled", "canceled", "shipped"][i % 6], 10.0 + i, f"2024-0{1 + i % 3}-15", i % 2)
        for i in range(40)
    ]
    rows.append(("o40", None, 99.5, "2024-03-31", 0))
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", rows)
    conn.execute("CREATE VIEW v_status AS SELECT status, COUNT(*) AS orders FROM orders GROUP BY status")
    conn.commit()
    conn.close()
    return Database("sqlite", str(path))


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.message = None

    def call_tool(self, system, message, tool, usage, max_tokens):
        self.message = message
        return self.reply


DRAFT = {
    "display_name": "Shop orders",
    "description": "Orders from a small web shop.",
    "currency": "EUR",
    "data_range": {"from": "2024-01-15", "to": "2024-03-31"},
    "tables": [
        {
            "name": "orders",
            "grain": "one row per order",
            "description": "Every order with its status and amount.",
            "columns": [
                {"name": "order_id", "description": "order id"},
                {"name": "status", "description": "order status"},
                {"name": "amount", "description": "order value in EUR"},
                {"name": "made_up_column", "description": "should be ignored"},
            ],
        }
    ],
    "rules": ["Revenue means amount on delivered orders."],
    "examples": [
        {"question": "How many orders are there?", "sql": "SELECT COUNT(*) AS orders FROM orders"},
        {"question": "Revenue by status", "sql": "SELECT status, SUM(amount) AS revenue FROM orders GROUP BY status"},
        {"question": "Broken column", "sql": "SELECT missing FROM orders"},
        {"question": "System table", "sql": "SELECT name FROM sqlite_master"},
    ],
    "suggested_questions": ["How many orders were late?"],
}


def test_lists_tables_and_columns(shop_db):
    tables = list_columns(shop_db)
    assert list(tables) == ["orders", "v_status"]
    assert [c for c, _ in tables["orders"]] == ["order_id", "status", "amount", "ordered_at", "is_late"]


def test_profiles_columns(shop_db):
    profile = profile_table(shop_db, "orders", list_columns(shop_db)["orders"])
    columns = {c.name: c for c in profile.columns}

    assert profile.row_count == 41
    assert columns["order_id"].distinct == 41
    assert columns["order_id"].top_values == []
    assert columns["status"].null_pct == 2.4
    assert columns["status"].top_values == ["delivered", "canceled", "shipped"]
    assert (columns["amount"].min, columns["amount"].max) == (10.0, 99.5)
    assert set(columns["is_late"].top_values) == {0, 1}
    assert "status (TEXT), 3 distinct" in describe_profile(profile)


def test_draft_keeps_database_columns_and_working_examples(shop_db, tmp_path):
    tables = list_columns(shop_db)
    profiles = [profile_table(shop_db, name, cols) for name, cols in tables.items()]
    llm = FakeLLM(DRAFT)

    draft = draft_pack("shop", profiles, shop_db, llm)

    assert "Table orders: 41 rows" in llm.message
    orders = draft.semantic["tables"][0]
    assert [c["name"] for c in orders["columns"]] == ["order_id", "status", "amount", "ordered_at", "is_late"]
    assert orders["columns"][2]["description"] == "order value in EUR"
    assert orders["columns"][1]["values"] == ["delivered", "canceled", "shipped"]
    assert draft.semantic["tables"][1]["description"] == ""

    assert [e["question"] for e in draft.examples["examples"]] == ["How many orders are there?", "Revenue by status"]
    assert [q for q, _ in draft.rejected_examples] == ["Broken column", "System table"]


def test_written_draft_loads_as_a_pack(shop_db, tmp_path):
    profiles = [profile_table(shop_db, name, cols) for name, cols in list_columns(shop_db).items()]
    draft = draft_pack("shop", profiles, shop_db, FakeLLM(DRAFT))
    write_draft(draft, tmp_path / "shop")

    pack = load_pack(tmp_path / "shop")
    assert pack.display_name == "Shop orders"
    assert pack.allowed_tables == {"orders", "v_status"}
    assert pack.suggested_questions == ["How many orders were late?"]
    assert (tmp_path / "shop" / "semantic.yaml").read_text().startswith("# Drafted by askit init")
    for example in pack.examples:
        check_sql(example.sql, "sqlite", pack.allowed_tables)
    assert "Revenue means amount" in build_system_prompt(pack, "sqlite")


def test_draft_without_llm(shop_db, tmp_path):
    profiles = [profile_table(shop_db, "orders", list_columns(shop_db)["orders"])]
    draft = draft_pack("shop", profiles, shop_db, llm=None)

    assert draft.examples["examples"] == []
    assert all(c["description"] == "" for c in draft.semantic["tables"][0]["columns"])
    write_draft(draft, tmp_path / "shop")
    assert load_pack(tmp_path / "shop").allowed_tables == {"orders"}

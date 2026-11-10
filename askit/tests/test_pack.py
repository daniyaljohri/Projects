import pytest
import sqlglot
from sqlglot import exp

from askit.config import PROJECT_ROOT
from askit.guardrails import check_sql
from askit.pack import load_pack
from askit.prompt import build_system_prompt

PACK = load_pack(PROJECT_ROOT / "packs" / "olist")


def test_pack_lists_the_five_chatbot_views():
    assert PACK.allowed_tables == {
        "chatbot.v_orders_full",
        "chatbot.v_customer_summary",
        "chatbot.v_seller_summary",
        "chatbot.v_product_summary",
        "chatbot.v_monthly_trends",
    }


@pytest.mark.parametrize("example", PACK.examples, ids=lambda e: e.question[:40])
def test_examples_pass_the_guardrails(example):
    check_sql(example.sql, PACK.examples_dialect, PACK.allowed_tables)


@pytest.mark.parametrize("example", PACK.examples, ids=lambda e: e.question[:40])
def test_examples_only_use_documented_columns(example):
    tree = sqlglot.parse_one(example.sql, read=PACK.examples_dialect)
    tables = {t.name.lower(): t for t in PACK.tables}
    used = {f"{t.db}.{t.name}".lower() for t in tree.find_all(exp.Table) if t.db}
    known = {c.name.lower() for name in used for c in tables[name].columns}
    aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)}

    unknown = {c.name.lower() for c in tree.find_all(exp.Column)} - known - aliases
    assert not unknown, f"columns not in semantic.yaml: {sorted(unknown)}"


@pytest.mark.parametrize("dialect", ["tsql", "sqlite"])
def test_prompt_builds_with_every_table(dialect):
    prompt = build_system_prompt(PACK, dialect)
    for name in PACK.allowed_tables:
        assert name in prompt
    assert "## Business rules" in prompt
    assert "## Examples" in prompt


def test_sqlite_prompt_translates_examples():
    prompt = build_system_prompt(PACK, "sqlite")
    examples = prompt.split("## Examples", 1)[1]
    assert "LIMIT 10" in examples
    assert "TOP 10" not in examples

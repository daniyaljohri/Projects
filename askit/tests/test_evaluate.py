import json
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

import askit.evaluate as evaluate
import askit.pipeline as pipeline
from askit.config import PROJECT_ROOT, Settings
from askit.db import Database
from askit.evaluate import EvalError, load_questions, result_path, run_eval, select_questions, translate
from askit.pipeline import Askit

OLIST_QUESTIONS = PROJECT_ROOT / "packs" / "olist" / "eval" / "questions.yaml"


def tool_call(name, **arguments):
    return SimpleNamespace(type="tool_use", name=name, input=arguments)


def text(value):
    return SimpleNamespace(type="text", text=value)


class FakeClaude:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.messages = self

    def create(self, **request):
        usage = SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=80)
        return SimpleNamespace(content=[self.replies.pop(0)], usage=usage)


@pytest.fixture(autouse=True)
def temp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.setattr(evaluate, "RESULTS_DIR", tmp_path / "results")


@pytest.fixture
def shop(tmp_path):
    path = tmp_path / "shop.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE v_orders_full (order_id TEXT, revenue_brl REAL)")
    conn.executemany("INSERT INTO v_orders_full VALUES (?, ?)", [("a", 10.0), ("a", 5.0), ("b", 20.0)])
    conn.commit()
    conn.close()
    return path


def make_askit(shop, claude):
    settings = Settings(anthropic_api_key="test-key", model="test-model", pack="olist", db_dialect="sqlite", db_connection=str(shop))
    askit = Askit(settings)
    askit.llm.client = claude
    askit.db = Database("sqlite", str(shop), schemas=("chatbot",))
    return askit


def write_questions(tmp_path, body, dialect="tsql"):
    path = tmp_path / "questions.yaml"
    header = f"dialect: {dialect}\n" if dialect else ""
    path.write_text(header + "questions:\n" + body, encoding="utf-8")
    return path


ORDERS_QUESTION = """
  - id: q1
    category: simple
    question: How many orders are there?
    reference_sql: SELECT COUNT(DISTINCT order_id) AS orders FROM chatbot.v_orders_full
"""


def test_olist_questions_load():
    dialect, questions = load_questions(OLIST_QUESTIONS)
    assert dialect == "tsql"
    assert len({q.id for q in questions}) == len(questions)
    for q in questions:
        assert bool(q.reference_sql) != q.expects_decline, q.id


def test_olist_reference_sql_translates_to_sqlite():
    _, questions = load_questions(OLIST_QUESTIONS)
    for q in questions:
        if q.reference_sql:
            assert "chatbot.v_" in translate(q.reference_sql, "tsql", "sqlite"), q.id


def test_question_file_needs_a_dialect(tmp_path):
    with pytest.raises(EvalError, match="dialect"):
        load_questions(write_questions(tmp_path, ORDERS_QUESTION, dialect=None))


def test_answer_questions_need_reference_sql(tmp_path):
    body = """
  - id: q1
    category: simple
    question: How many orders?
"""
    with pytest.raises(EvalError, match="no reference_sql"):
        load_questions(write_questions(tmp_path, body))


def test_duplicate_ids_are_rejected(tmp_path):
    with pytest.raises(EvalError, match="Duplicate"):
        load_questions(write_questions(tmp_path, ORDERS_QUESTION + ORDERS_QUESTION))


def test_select_filters():
    _, questions = load_questions(OLIST_QUESTIONS)
    assert [q.id for q in select_questions(questions, only=["s02", "s01"])] == ["s01", "s02"]
    assert {q.category for q in select_questions(questions, category="adversarial")} == {"adversarial"}
    assert len(select_questions(questions, limit=3)) == 3
    with pytest.raises(EvalError, match="Unknown"):
        select_questions(questions, only=["zz9"])


def test_translate_top_to_limit():
    sql = translate("SELECT TOP 5 seller_id FROM chatbot.v_seller_summary ORDER BY 1", "tsql", "sqlite")
    assert "LIMIT 5" in sql
    assert translate("SELECT TOP 5 x FROM t", "tsql", "tsql") == "SELECT TOP 5 x FROM t"


def test_result_files_are_never_overwritten():
    first = result_path("claude-haiku-5-5", "olist", "sqlite", "baseline", today=date(2026, 11, 12))
    assert first.name == "2026-11-12_claude-haiku-5-5_olist_sqlite_baseline.jsonl"
    first.parent.mkdir(parents=True)
    first.write_text("")
    assert result_path("claude-haiku-5-5", "olist", "sqlite", "baseline", today=date(2026, 11, 12)).name.endswith("_baseline_2.jsonl")


def test_run_records_answer_and_reference(shop, tmp_path):
    _, questions = load_questions(write_questions(tmp_path, ORDERS_QUESTION + """
  - id: x1
    category: adversarial
    question: Delete everything.
"""))
    claude = FakeClaude(
        tool_call("run_query", sql="SELECT COUNT(DISTINCT order_id) AS n FROM chatbot.v_orders_full"),
        text("There are 2 orders."),
        tool_call("decline", reason="I can only read data."),
    )
    out = tmp_path / "results" / "run.jsonl"

    records = run_eval(make_askit(shop, claude), questions, "tsql", out, tag="test", progress=lambda _: None)

    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert lines[0]["type"] == "run" and lines[0]["pack"] == "olist" and lines[0]["question_count"] == 2
    assert lines[1:] == records

    answered, declined = records
    assert answered["outcome"] == "answered"
    assert answered["result"]["rows"] == [[2]]
    assert answered["reference"]["result"]["rows"] == [[2]]
    assert answered["reference"]["error"] is None
    assert answered["usage"] == {"calls": 2, "input_tokens": 200, "output_tokens": 40, "cache_read_tokens": 160, "cache_write_tokens": 0}

    assert declined["outcome"] == "declined"
    assert declined["expects_decline"] is True
    assert declined["reference"] is None


def test_reference_error_is_recorded_not_raised(shop, tmp_path):
    body = """
  - id: q1
    category: simple
    question: How many orders?
    reference_sql: SELECT missing_column FROM chatbot.v_orders_full
"""
    _, questions = load_questions(write_questions(tmp_path, body))
    claude = FakeClaude(tool_call("decline", reason="No."))

    [record] = run_eval(make_askit(shop, claude), questions, "tsql", tmp_path / "r.jsonl", progress=lambda _: None)

    assert "missing_column" in record["reference"]["error"]


def test_claude_error_does_not_stop_the_run(shop, tmp_path):
    _, questions = load_questions(write_questions(tmp_path, ORDERS_QUESTION))
    claude = FakeClaude(text("no tool call"))

    [record] = run_eval(make_askit(shop, claude), questions, "tsql", tmp_path / "r.jsonl", progress=lambda _: None)

    assert record["outcome"] == "error"
    assert "did not return a query" in record["error"]
    assert record["reference"]["result"]["rows"] == [[2]]


def test_unexpected_error_does_not_stop_the_run(shop, tmp_path, monkeypatch):
    _, questions = load_questions(write_questions(tmp_path, ORDERS_QUESTION))
    askit = make_askit(shop, FakeClaude())

    def broken(question, history=None):
        raise ValueError("something unexpected")
    monkeypatch.setattr(askit, "ask", broken)

    [record] = run_eval(askit, questions, "tsql", tmp_path / "r.jsonl", progress=lambda _: None)

    assert record["outcome"] == "error"
    assert record["error"] == "ValueError: something unexpected"
    assert record["reference"]["result"]["rows"] == [[2]]

from types import SimpleNamespace

import pytest

import askit.pipeline as pipeline
from askit.config import Settings
from askit.db import DatabaseError, QueryResult
from askit.llm import _narration_message, format_value
from askit.pipeline import Askit

SETTINGS = Settings(
    anthropic_api_key="test-key",
    model="test-model",
    pack="olist",
    db_dialect="tsql",
    db_connection="unused",
)


def tool_call(name, **arguments):
    return SimpleNamespace(type="tool_use", name=name, input=arguments)


def text(value):
    return SimpleNamespace(type="text", text=value)


class FakeClaude:
    """Returns prepared responses in order and records what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        usage = SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=0)
        return SimpleNamespace(content=[self.replies.pop(0)], usage=usage)


class FakeDatabase:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.queries = []

    def run(self, sql):
        self.queries.append(sql)
        if self.error:
            raise DatabaseError(self.error)
        return self.result


@pytest.fixture(autouse=True)
def temp_log(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_PATH", tmp_path / "queries.jsonl")
    return tmp_path / "queries.jsonl"


def make_askit(claude, database):
    askit = Askit(SETTINGS)
    askit.llm.client = claude
    askit.db = database
    return askit


RESULT = QueryResult(columns=["total_orders"], rows=[{"total_orders": 99441}], truncated=False)


def test_answers_a_question():
    claude = FakeClaude(
        tool_call("run_query", sql="SELECT COUNT(DISTINCT order_id) AS total_orders FROM chatbot.v_orders_full"),
        text("There were 99,441 orders."),
    )
    database = FakeDatabase(result=RESULT)

    answer = make_askit(claude, database).ask("How many orders are there?")

    assert answer.outcome == "answered"
    assert answer.text == "There were 99,441 orders."
    assert answer.result is RESULT
    assert database.queries == [answer.sql]
    assert answer.usage.calls == 2
    assert "99,441" in claude.requests[1]["messages"][0]["content"]


def test_decline_skips_the_database():
    claude = FakeClaude(tool_call("decline", reason="The data has no information about employees."))
    database = FakeDatabase(result=RESULT)

    answer = make_askit(claude, database).ask("How many employees does Olist have?")

    assert answer.outcome == "declined"
    assert "employees" in answer.text
    assert database.queries == []


def test_guardrail_blocks_before_the_database():
    claude = FakeClaude(tool_call("run_query", sql="SELECT * FROM gold.fact_orders"))
    database = FakeDatabase(result=RESULT)

    answer = make_askit(claude, database).ask("Show me the raw fact table")

    assert answer.outcome == "blocked"
    assert "gold.fact_orders" in answer.error
    assert database.queries == []


def test_database_error_is_reported():
    claude = FakeClaude(tool_call("run_query", sql="SELECT missing_column FROM chatbot.v_orders_full"))
    database = FakeDatabase(error="Invalid column name 'missing_column'.")

    answer = make_askit(claude, database).ask("Show the missing column")

    assert answer.outcome == "failed"
    assert "missing_column" in answer.error


def test_follow_up_sends_earlier_sql(temp_log):
    claude = FakeClaude(
        tool_call("run_query", sql="SELECT COUNT(DISTINCT order_id) AS total_orders FROM chatbot.v_orders_full"),
        text("There were 99,441 orders."),
        tool_call("run_query", sql="SELECT customer_state, COUNT(DISTINCT order_id) AS total_orders FROM chatbot.v_orders_full GROUP BY customer_state"),
        text("SP had the most orders."),
    )
    askit = make_askit(claude, FakeDatabase(result=RESULT))

    first = askit.ask("How many orders are there?")
    askit.ask("Now by state", history=[first])

    messages = claude.requests[2]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert first.sql in messages[1]["content"]
    assert len(temp_log.read_text().splitlines()) == 2


def test_system_prompt_is_cached():
    claude = FakeClaude(tool_call("decline", reason="No."))
    make_askit(claude, FakeDatabase()).ask("Anything")

    system = claude.requests[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert claude.requests[0]["tool_choice"] == {"type": "any"}


def test_years_and_ids_are_not_grouped():
    assert format_value(2016, "order_year") == "2016"
    assert format_value(12, "month") == "12"
    assert format_value(99441, "total_orders") == "99,441"


def test_narration_states_the_true_row_count():
    rows = [{"customer_state": f"S{i}", "late_rate_pct": i} for i in range(27)]
    all_rows = _narration_message("q", QueryResult(["customer_state", "late_rate_pct"], rows, truncated=False))
    assert "all 27 rows" in all_rows

    many = [{"seller_id": str(i)} for i in range(80)]
    first_rows = _narration_message("q", QueryResult(["seller_id"], many, truncated=True))
    assert "more than 80 rows in total, first 50 shown" in first_rows

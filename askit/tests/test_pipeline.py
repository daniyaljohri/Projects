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
    def __init__(self, result=None, error=None, failures=None, retryable=True):
        self.result = result
        self.error = error
        # fail this many times, then succeed; None means fail every time
        self.failures = failures
        self.retryable = retryable
        self.queries = []

    def run(self, sql):
        self.queries.append(sql)
        if self.error and (self.failures is None or len(self.queries) <= self.failures):
            raise DatabaseError(self.error, retryable=self.retryable)
        return self.result


@pytest.fixture(autouse=True)
def temp_log(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_PATH", tmp_path / "queries.jsonl")
    return tmp_path / "queries.jsonl"


def make_askit(claude, database, settings=SETTINGS):
    askit = Askit(settings)
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


def test_database_error_is_reported_once_retries_run_out():
    claude = FakeClaude(
        tool_call("run_query", sql="SELECT missing_column FROM chatbot.v_orders_full"),
        tool_call("run_query", sql="SELECT missing_column FROM chatbot.v_orders_full"),
    )
    database = FakeDatabase(error="Invalid column name 'missing_column'.")

    answer = make_askit(claude, database).ask("Show the missing column")

    assert answer.outcome == "failed"
    assert "missing_column" in answer.error
    assert answer.retries == 1
    assert len(database.queries) == 2


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


# retry on error

GOOD_SQL = "SELECT COUNT(DISTINCT order_id) AS total_orders FROM chatbot.v_orders_full"


def test_unreadable_sql_is_sent_back_and_fixed():
    claude = FakeClaude(
        tool_call("run_query", sql=GOOD_SQL + ' "'),
        tool_call("run_query", sql=GOOD_SQL),
        text("There were 99,441 orders."),
    )
    database = FakeDatabase(result=RESULT)

    answer = make_askit(claude, database).ask("How many orders are there?")

    assert answer.outcome == "answered"
    assert answer.retries == 1
    assert answer.usage.calls == 3
    assert database.queries == [GOOD_SQL]
    fix_messages = claude.requests[1]["messages"]
    assert fix_messages[0]["content"] == "How many orders are there?"
    assert GOOD_SQL + ' "' in fix_messages[1]["content"]
    assert "could not be parsed" in fix_messages[2]["content"]


def test_database_error_is_sent_back_and_fixed():
    claude = FakeClaude(
        tool_call("run_query", sql="SELECT seller_tier FROM chatbot.v_orders_full"),
        tool_call("run_query", sql="SELECT seller_tier FROM chatbot.v_seller_summary"),
        text("Fixed."),
    )
    database = FakeDatabase(result=RESULT, error="no such column: seller_tier", failures=1)

    answer = make_askit(claude, database).ask("Which tiers are there?")

    assert answer.outcome == "answered"
    assert answer.retries == 1
    assert "no such column: seller_tier" in claude.requests[1]["messages"][2]["content"]


def test_safety_block_is_never_retried():
    claude = FakeClaude(tool_call("run_query", sql="SELECT * FROM gold.fact_orders"))
    database = FakeDatabase(result=RESULT)

    answer = make_askit(claude, database).ask("Show me the raw fact table")

    assert answer.outcome == "blocked"
    assert answer.retries == 0
    assert len(claude.requests) == 1


def test_write_is_never_retried():
    claude = FakeClaude(tool_call("run_query", sql="DELETE FROM chatbot.v_orders_full"))

    answer = make_askit(claude, FakeDatabase(result=RESULT)).ask("Delete the orders")

    assert answer.outcome == "blocked"
    assert len(claude.requests) == 1


def test_lost_connection_is_not_retried():
    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL))
    database = FakeDatabase(error="Could not connect", retryable=False)

    answer = make_askit(claude, database).ask("How many orders are there?")

    assert answer.outcome == "failed"
    assert answer.retries == 0
    assert len(claude.requests) == 1


def test_claude_may_decline_after_seeing_the_error():
    claude = FakeClaude(
        tool_call("run_query", sql="SELECT employees FROM chatbot.v_orders_full"),
        tool_call("decline", reason="There is no employee data."),
    )
    database = FakeDatabase(error="no such column: employees")

    answer = make_askit(claude, database).ask("How many employees?")

    assert answer.outcome == "declined"
    assert answer.retries == 1


def test_retries_can_be_turned_off():
    from dataclasses import replace

    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL + ' "'))

    answer = make_askit(claude, FakeDatabase(result=RESULT), replace(SETTINGS, sql_retries=0)).ask("How many orders?")

    assert answer.outcome == "blocked"
    assert answer.retries == 0
    assert len(claude.requests) == 1


def test_retries_are_logged(temp_log):
    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL + ' "'), tool_call("run_query", sql=GOOD_SQL), text("ok"))
    make_askit(claude, FakeDatabase(result=RESULT)).ask("How many orders?")

    import json
    assert json.loads(temp_log.read_text())["retries"] == 1


def test_retry_setting_comes_from_the_environment(monkeypatch):
    from askit.config import ConfigError, get_settings

    for name, value in [("ASKIT_DB_DIALECT", "sqlite"), ("ASKIT_DB_CONNECTION", "data/x.sqlite"), ("ASKIT_MODEL", "m"), ("ASKIT_PACK", "olist")]:
        monkeypatch.setenv(name, value)

    get_settings.cache_clear()
    monkeypatch.delenv("ASKIT_SQL_RETRIES", raising=False)
    assert get_settings().sql_retries == 1

    get_settings.cache_clear()
    monkeypatch.setenv("ASKIT_SQL_RETRIES", "0")
    assert get_settings().sql_retries == 0

    for bad in ("-1", "two", "9"):
        get_settings.cache_clear()
        monkeypatch.setenv("ASKIT_SQL_RETRIES", bad)
        with pytest.raises(ConfigError, match="ASKIT_SQL_RETRIES"):
            get_settings()
    get_settings.cache_clear()


# schema retrieval

def test_retrieval_off_sends_the_whole_cached_prompt():
    claude = FakeClaude(tool_call("decline", reason="No."))
    askit = make_askit(claude, FakeDatabase())
    answer = askit.ask("Anything")

    system = claude.requests[0]["system"]
    assert len(system) == 1 and system[0]["text"] == askit.system_prompt
    assert answer.tables == []


def test_retrieval_sends_only_the_chosen_tables():
    from dataclasses import replace

    claude = FakeClaude(tool_call("decline", reason="No."))
    settings = replace(SETTINGS, schema_retrieval="keyword", schema_top_k=1)
    answer = make_askit(claude, FakeDatabase(), settings).ask("Which seller tier has the most cancelled orders?")

    head, tables = claude.requests[0]["system"]
    assert head["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in tables
    assert "### chatbot.v_seller_summary" in tables["text"]
    assert "### chatbot.v_orders_full" not in tables["text"] + head["text"]
    assert "## Business rules" in head["text"] and "## Examples" in head["text"]
    assert answer.tables == ["chatbot.v_seller_summary"]


def test_retry_uses_the_same_tables():
    from dataclasses import replace

    claude = FakeClaude(
        tool_call("run_query", sql="SELECT seller_tier FROM chatbot.v_seller_summary \""),
        tool_call("run_query", sql="SELECT seller_tier FROM chatbot.v_seller_summary"),
        text("ok"),
    )
    settings = replace(SETTINGS, schema_retrieval="keyword", schema_top_k=1)
    make_askit(claude, FakeDatabase(result=RESULT), settings).ask("Which seller tier has the most cancelled orders?")

    assert claude.requests[0]["system"] == claude.requests[1]["system"]


def test_follow_up_keeps_the_earlier_question_for_retrieval():
    from dataclasses import replace

    claude = FakeClaude(
        tool_call("run_query", sql="SELECT seller_tier FROM chatbot.v_seller_summary"), text("ok"),
        tool_call("decline", reason="No."),
    )
    settings = replace(SETTINGS, schema_retrieval="keyword", schema_top_k=1)
    askit = make_askit(claude, FakeDatabase(result=RESULT), settings)
    first = askit.ask("Which seller tier has the most cancelled orders?")
    follow_up = askit.ask("and now just for RJ", history=[first])

    assert follow_up.tables == ["chatbot.v_seller_summary"]


def test_retrieval_settings_come_from_the_environment(monkeypatch):
    from askit.config import ConfigError, get_settings

    for name, value in [("ASKIT_DB_DIALECT", "sqlite"), ("ASKIT_DB_CONNECTION", "data/x.sqlite"), ("ASKIT_MODEL", "m"), ("ASKIT_PACK", "olist")]:
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ASKIT_SQL_RETRIES", raising=False)

    get_settings.cache_clear()
    monkeypatch.delenv("ASKIT_SCHEMA_RETRIEVAL", raising=False)
    monkeypatch.delenv("ASKIT_SCHEMA_TOP_K", raising=False)
    settings = get_settings()
    assert (settings.schema_retrieval, settings.schema_top_k) == ("off", 3)

    get_settings.cache_clear()
    monkeypatch.setenv("ASKIT_SCHEMA_RETRIEVAL", "Hybrid")
    monkeypatch.setenv("ASKIT_SCHEMA_TOP_K", "2")
    settings = get_settings()
    assert (settings.schema_retrieval, settings.schema_top_k) == ("hybrid", 2)

    for name, bad in [("ASKIT_SCHEMA_RETRIEVAL", "magic"), ("ASKIT_SCHEMA_TOP_K", "0")]:
        get_settings.cache_clear()
        monkeypatch.setenv(name, bad)
        with pytest.raises(ConfigError, match=name):
            get_settings()
        monkeypatch.setenv(name, "keyword" if name == "ASKIT_SCHEMA_RETRIEVAL" else "2")
    get_settings.cache_clear()


# self-check

FIVE_MONTHS = QueryResult(columns=["month", "revenue"], rows=[{"month": m, "revenue": 1.0} for m in range(5)], truncated=False)
ONE_MONTH = QueryResult(columns=["month", "revenue"], rows=[{"month": 11, "revenue": 9.0}], truncated=False)


class SequenceDatabase:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.queries = []

    def run(self, sql):
        self.queries.append(sql)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def checking(settings=SETTINGS):
    from dataclasses import replace
    return replace(settings, self_check=True)


def test_self_check_off_makes_no_extra_call():
    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL), text("ok"))
    answer = make_askit(claude, FakeDatabase(result=RESULT)).ask("How many orders?")
    assert answer.self_check == "" and answer.usage.calls == 2


def test_self_check_accepts_a_good_answer():
    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL), tool_call("accept_result"), text("ok"))
    answer = make_askit(claude, FakeDatabase(result=RESULT), checking()).ask("How many orders?")

    assert answer.self_check == "accepted"
    assert answer.usage.calls == 3
    assert answer.first_sql is None
    check = claude.requests[1]
    assert {tool["name"] for tool in check["tools"]} == {"accept_result", "run_query"}
    assert "1 rows. Columns: total_orders" in check["messages"][-1]["content"]


def test_self_check_revises_the_wrong_shape():
    top5 = "SELECT month, revenue FROM chatbot.v_monthly_trends ORDER BY revenue DESC LIMIT 5"
    top1 = "SELECT month, revenue FROM chatbot.v_monthly_trends ORDER BY revenue DESC LIMIT 1"
    claude = FakeClaude(tool_call("run_query", sql=top5), tool_call("run_query", sql=top1), text("November."))
    database = SequenceDatabase(FIVE_MONTHS, ONE_MONTH)

    answer = make_askit(claude, database, checking()).ask("Which month had the highest revenue?")

    assert answer.self_check == "revised"
    assert answer.sql == top1 and answer.result is ONE_MONTH
    assert answer.first_sql == top5 and answer.first_result is FIVE_MONTHS
    assert "5 rows" in claude.requests[1]["messages"][-1]["content"]
    assert "1 rows" in claude.requests[2]["messages"][0]["content"]


def test_correction_that_fails_keeps_the_original():
    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL), tool_call("run_query", sql="SELECT nope FROM chatbot.v_orders_full"), text("ok"))
    database = SequenceDatabase(RESULT, DatabaseError("no such column: nope"))

    answer = make_askit(claude, database, checking()).ask("How many orders?")

    assert answer.outcome == "answered" and answer.self_check == "kept"
    assert answer.sql == GOOD_SQL and answer.result is RESULT


def test_correction_is_still_checked_by_the_guardrails():
    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL), tool_call("run_query", sql="DELETE FROM chatbot.v_orders_full"), text("ok"))
    database = SequenceDatabase(RESULT)

    answer = make_askit(claude, database, checking()).ask("How many orders?")

    assert answer.self_check == "kept" and database.queries == [GOOD_SQL]


def test_unchanged_sql_counts_as_accepted():
    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL), tool_call("run_query", sql=GOOD_SQL + "  "), text("ok"))
    database = SequenceDatabase(RESULT)

    answer = make_askit(claude, database, checking()).ask("How many orders?")

    assert answer.self_check == "accepted" and database.queries == [GOOD_SQL]


def test_declines_are_not_checked():
    claude = FakeClaude(tool_call("decline", reason="No employee data."))
    answer = make_askit(claude, FakeDatabase(), checking()).ask("How many employees?")
    assert answer.self_check == "" and len(claude.requests) == 1


def test_self_check_setting_comes_from_the_environment(monkeypatch):
    from askit.config import ConfigError, get_settings

    for name, value in [("ASKIT_DB_DIALECT", "sqlite"), ("ASKIT_DB_CONNECTION", "data/x.sqlite"), ("ASKIT_MODEL", "m"), ("ASKIT_PACK", "olist")]:
        monkeypatch.setenv(name, value)
    for name in ("ASKIT_SQL_RETRIES", "ASKIT_SCHEMA_RETRIEVAL", "ASKIT_SCHEMA_TOP_K", "ASKIT_SELF_CHECK"):
        monkeypatch.delenv(name, raising=False)

    get_settings.cache_clear()
    assert get_settings().self_check is False
    get_settings.cache_clear()
    monkeypatch.setenv("ASKIT_SELF_CHECK", "On")
    assert get_settings().self_check is True
    get_settings.cache_clear()
    monkeypatch.setenv("ASKIT_SELF_CHECK", "maybe")
    with pytest.raises(ConfigError, match="ASKIT_SELF_CHECK"):
        get_settings()
    get_settings.cache_clear()


def test_check_can_use_a_different_model():
    from dataclasses import replace

    writer = FakeClaude(tool_call("run_query", sql=GOOD_SQL), text("ok"))
    reviewer = FakeClaude(tool_call("accept_result"))
    askit = make_askit(writer, FakeDatabase(result=RESULT), replace(SETTINGS, self_check=True, check_model="bigger-model"))
    askit.checker.client = reviewer

    answer = askit.ask("How many orders?")

    assert askit.checker is not askit.llm and askit.checker.model == "bigger-model"
    assert len(writer.requests) == 2 and len(reviewer.requests) == 1
    assert answer.self_check == "accepted"
    assert answer.check_usage.calls == 1 and answer.usage.calls == 3


def test_same_check_model_reuses_the_writer():
    from dataclasses import replace

    claude = FakeClaude(tool_call("run_query", sql=GOOD_SQL), tool_call("accept_result"), text("ok"))
    askit = make_askit(claude, FakeDatabase(result=RESULT), replace(SETTINGS, self_check=True, check_model="test-model"))

    askit.ask("How many orders?")

    assert askit.checker is askit.llm and len(claude.requests) == 3


def test_failed_check_keeps_the_answer_and_says_why():
    from dataclasses import replace
    import anthropic

    class BrokenChecker:
        def __init__(self):
            self.messages = self

        def create(self, **request):
            raise anthropic.APIError("model not found: bigger-model", request=None, body=None)

    writer = FakeClaude(tool_call("run_query", sql=GOOD_SQL), text("ok"))
    askit = make_askit(writer, FakeDatabase(result=RESULT), replace(SETTINGS, self_check=True, check_model="bigger-model"))
    askit.checker.client = BrokenChecker()

    answer = askit.ask("How many orders?")

    assert answer.outcome == "answered" and answer.result is RESULT
    assert answer.self_check == "failed" and "model not found" in answer.check_error


def _refuses_forced_tools():
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(400, request=request)
    return anthropic.BadRequestError(
        "Error code: 400 - tool_choice: type \"tool\" and \"any\" are not supported for this model.",
        response=response, body=None)


class AutoOnlyClaude(FakeClaude):
    """Like a model that rejects tool_choice any/tool but answers with tool_choice auto."""

    def create(self, **request):
        if request.get("tool_choice", {}).get("type") in ("any", "tool"):
            self.requests.append(request)
            raise _refuses_forced_tools()
        return super().create(**request)


def test_model_that_refuses_forced_tools_falls_back_to_auto():
    claude = AutoOnlyClaude(tool_call("run_query", sql=GOOD_SQL), text("ok"), tool_call("decline", reason="No."))
    askit = make_askit(claude, FakeDatabase(result=RESULT))

    first = askit.ask("How many orders?")
    second = askit.ask("How many employees?")

    assert first.outcome == "answered" and second.outcome == "declined"
    choices = [r.get("tool_choice", {}).get("type") for r in claude.requests if "tools" in r]
    # one refused call, then auto for the rest of the session
    assert choices == ["any", "auto", "auto"]
    assert askit.llm.forced_tools is False


def test_other_bad_requests_are_still_errors():
    import anthropic
    import httpx

    class Broken(FakeClaude):
        def create(self, **request):
            response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
            raise anthropic.BadRequestError("Error code: 400 - prompt is too long", response=response, body=None)

    askit = make_askit(Broken(), FakeDatabase(result=RESULT))
    with pytest.raises(Exception, match="prompt is too long"):
        askit.ask("How many orders?")

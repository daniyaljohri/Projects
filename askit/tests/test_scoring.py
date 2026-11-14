import json

import pytest

from askit.evaluate import EvalError
from askit.scoring import compare_results, estimate_cost, load_run, score_record, summarise, write_summary


def result(columns, rows, truncated=False):
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated, "rows_cut": False}


def record(id="q1", category="simple", outcome="answered", answer=None, reference=None, order_matters=False, expects_decline=False, error=None):
    return {
        "type": "question", "id": id, "category": category, "question": f"Question {id}?",
        "order_matters": order_matters, "expects_decline": expects_decline,
        "outcome": outcome, "text": "", "sql": None, "error": error,
        "result": answer, "seconds": 1.5,
        "usage": {"calls": 2, "input_tokens": 400, "output_tokens": 100, "cache_read_tokens": 5800, "cache_write_tokens": 0},
        "reference": None if expects_decline else {"sql": "SELECT 1", "error": None, "result": reference},
    }


def matches(answer, reference, order_matters=False):
    return compare_results(answer, reference, order_matters)[0]


# refusals

@pytest.mark.parametrize("outcome", ["declined", "blocked"])
def test_refusal_questions_pass_when_refused(outcome):
    assert score_record(record(category="adversarial", outcome=outcome, expects_decline=True)).passed


def test_refusal_questions_fail_when_answered():
    score = score_record(record(category="out_of_scope", outcome="answered", expects_decline=True, answer=result(["n"], [[1]])))
    assert not score.passed and score.reason == "should_decline"


@pytest.mark.parametrize("outcome, reason", [("declined", "wrongly_declined"), ("blocked", "wrongly_blocked"), ("failed", "error"), ("error", "error")])
def test_answer_questions_fail_when_not_answered(outcome, reason):
    score = score_record(record(outcome=outcome, reference=result(["n"], [[1]])))
    assert score.passed is False and score.reason == reason


def test_reference_error_is_not_scored():
    rec = record(answer=result(["n"], [[1]]))
    rec["reference"] = {"sql": "SELECT x", "error": "no such column: x", "result": None}
    score = score_record(rec)
    assert score.passed is None and score.reason == "reference_error"


# columns

def test_column_names_are_ignored():
    assert matches(result(["orders"], [[98666]]), result(["total_orders"], [[98666]]))


def test_extra_columns_are_allowed():
    answer = result(["seller_id", "city", "revenue"], [["a", "guariba", 249640.7]])
    assert matches(answer, result(["seller_id", "total_revenue_brl"], [["a", 249640.7]]))


def test_missing_column_fails():
    ok, detail = compare_results(result(["seller_id"], [["a"]]), result(["seller_id", "revenue"], [["a", 10.5]]), False)
    assert not ok and "revenue" in detail


def test_columns_in_a_different_order():
    answer = result(["revenue", "year"], [[57183.21, 2016], [7142672.43, 2017]])
    assert matches(answer, result(["year", "revenue"], [[2016, 57183.21], [2017, 7142672.43]]))


def test_values_must_line_up_row_by_row():
    answer = result(["state", "rate"], [["AL", 2.8], ["AM", 21.4]])
    ok, detail = compare_results(answer, result(["state", "rate"], [["AL", 21.4], ["AM", 2.8]]), False)
    assert not ok and "row by row" in detail


# rows

def test_row_count_must_match():
    ok, detail = compare_results(result(["s"], [["a"], ["b"], ["c"]]), result(["s"], [["a"], ["b"]]), False)
    assert not ok and detail == "3 rows, expected 2"


def test_order_ignored_unless_it_matters():
    answer = result(["state"], [["RJ"], ["SP"]])
    reference = result(["state"], [["SP"], ["RJ"]])
    assert matches(answer, reference, order_matters=False)
    assert not matches(answer, reference, order_matters=True)


def test_empty_results_match():
    assert matches(result(["n"], []), result(["n"], []))


# values

def test_whole_numbers_must_be_exact():
    assert matches(result(["n"], [[98666]]), result(["n"], [[98666.0]]))
    assert not matches(result(["n"], [[2890]]), result(["n"], [[2887]]))


def test_decimals_allow_rounding():
    assert matches(result(["aov"], [[160.74]]), result(["aov"], [[160.73821664342165]]))
    assert matches(result(["rate"], [[6.8]]), result(["rate"], [[6.77252845208234]]))
    assert not matches(result(["rate"], [[7.0]]), result(["rate"], [[6.77252845208234]]))


def test_fraction_matches_percentage():
    assert matches(result(["rate"], [[0.0677252845208234]]), result(["rate_pct"], [[6.77252845208234]]))
    assert matches(result(["pct"], [[19.88]]), result(["share"], [[0.1987918837289441]]))


def test_text_ignores_case_and_spaces():
    assert matches(result(["c"], [["Bed_Bath_Table "]]), result(["c"], [["bed_bath_table"]]))


def test_timestamps_from_sql_server_and_sqlite_match():
    answer = result(["first", "last"], [["2016-09-04T21:15:19", "2018-09-03T09:06:57"]])
    reference = result(["first", "last"], [["2016-09-04 21:15:19", "2018-09-03 09:06:57.000"]])
    assert matches(answer, reference)


def test_nulls_match_nulls():
    assert matches(result(["c", "n"], [[None, 3]]), result(["c", "n"], [[None, 3]]))
    assert not matches(result(["c"], [["unknown"]]), result(["c"], [[None]]))


# summary

def test_cost_uses_the_price_table():
    tokens = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_tokens": 1_000_000, "cache_write_tokens": 0}
    assert estimate_cost("claude-haiku-5-5", tokens) == pytest.approx(0.61)
    assert estimate_cost("some-other-model", tokens) is None


def test_summary_reports_accuracy_failures_and_rules():
    run = {"type": "run", "started": "2026-11-11T18:00:00+00:00", "model": "claude-haiku-5-5", "pack": "olist",
           "dialect": "sqlite", "tag": "baseline", "questions_file": "packs/olist/eval/questions.yaml"}
    records = [
        record("s01", answer=result(["n"], [[98666]]), reference=result(["n"], [[98666]])),
        record("a02", category="aggregation", answer=result(["aov"], [[137.75]]), reference=result(["aov"], [[160.74]])),
        record("x01", category="adversarial", outcome="blocked", expects_decline=True),
    ]

    text = summarise(run, records)

    assert "**Accuracy: 2 of 3 (67%)**" in text
    assert "| aggregation | 1 | 0 | 0% |" in text
    assert "| a02 | aggregation | wrong_result |" in text
    assert "## Scoring rules" in text
    assert "Estimated cost: $" in text


def test_write_summary_rebuilds_from_the_file(tmp_path):
    path = tmp_path / "run.jsonl"
    run = {"type": "run", "started": "x", "model": "m", "pack": "p", "dialect": "sqlite", "tag": "", "questions_file": "q.yaml"}
    lines = [run, record(answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))]
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")

    summary = write_summary(path)

    assert summary == tmp_path / "run.md"
    assert "**Accuracy: 1 of 1 (100%)**" in summary.read_text(encoding="utf-8")
    assert "no price listed for m" in summary.read_text(encoding="utf-8")


def test_load_run_rejects_other_files(tmp_path):
    path = tmp_path / "other.jsonl"
    path.write_text('{"time": "x"}\n', encoding="utf-8")
    with pytest.raises(EvalError, match="not an evaluation result"):
        load_run(path)


def test_eval_report_command_works_without_settings(tmp_path, monkeypatch, capsys):
    from askit.cli import main

    for name in ("ANTHROPIC_API_KEY", "ASKIT_DB_DIALECT", "ASKIT_DB_CONNECTION", "ASKIT_MODEL", "ASKIT_PACK"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "run.jsonl"
    run = {"type": "run", "started": "x", "model": "claude-haiku-5-5", "pack": "olist", "dialect": "sqlite", "tag": "", "questions_file": "q.yaml"}
    lines = [run, record(answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))]
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")

    assert main(["eval-report", str(path)]) == 0
    assert "Accuracy: 1 of 1" in capsys.readouterr().out


def test_summary_counts_retries():
    run = {"type": "run", "started": "x", "model": "claude-haiku-5-5", "pack": "olist", "dialect": "sqlite", "tag": "", "questions_file": "q.yaml", "sql_retries": 1}
    fixed = record("c03", category="complex", answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))
    fixed["retries"] = 1
    still_wrong = record("c04", category="complex", outcome="failed", reference=result(["n"], [[1]]))
    still_wrong["retries"] = 1
    untouched = record("s01", answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))

    text = summarise(run, [fixed, still_wrong, untouched])

    assert "Retries after a failed query (up to 1 per question): 2 questions retried, 1 of them then passed" in text


def test_older_runs_without_retries_still_summarise():
    run = {"type": "run", "started": "x", "model": "m", "pack": "p", "dialect": "sqlite", "tag": "", "questions_file": "q.yaml"}
    text = summarise(run, [record(answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))])
    assert "up to 0 per question): 0 questions retried" in text


def test_summary_reports_schema_recall():
    run = {"type": "run", "started": "x", "model": "claude-haiku-5-5", "pack": "olist", "dialect": "sqlite", "tag": "",
           "questions_file": "q.yaml", "schema_retrieval": "hybrid", "schema_top_k": 2, "embedding_model": "BAAI/bge-small-en-v1.5"}
    covered = record("q1", answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))
    covered["reference"]["sql"] = "SELECT COUNT(*) FROM chatbot.v_seller_summary"
    covered["schema_tables"] = ["chatbot.v_seller_summary", "chatbot.v_orders_full"]
    missed = record("q2", answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))
    missed["reference"]["sql"] = "SELECT COUNT(*) FROM chatbot.v_monthly_trends"
    missed["schema_tables"] = ["chatbot.v_seller_summary", "chatbot.v_orders_full"]

    text = summarise(run, [covered, missed])

    assert "Schema retrieval: hybrid, BAAI/bge-small-en-v1.5, top 2 tables; every table the reference query needs was sent for 1 of 2 questions" in text


def test_summary_says_when_retrieval_is_off():
    run = {"type": "run", "started": "x", "model": "m", "pack": "p", "dialect": "sqlite", "tag": "", "questions_file": "q.yaml"}
    assert "Schema retrieval: off (every table sent)" in summarise(run, [record(answer=result(["n"], [[1]]), reference=result(["n"], [[1]]))])

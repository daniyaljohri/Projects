import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import sqlglot
import yaml

from askit.config import PROJECT_ROOT
from askit.db import DatabaseError, QueryResult
from askit.llm import LLMError
from askit.pipeline import Askit

RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
# these pass when Askit refuses, so they carry no reference query
DECLINE_CATEGORIES = ("out_of_scope", "adversarial")
# keeps result files small; a reference answer has a handful of rows, so a longer generated result is wrong anyway
STORED_ROWS = 500


class EvalError(Exception):
    pass


@dataclass
class Question:
    id: str
    category: str
    question: str
    reference_sql: str | None
    order_matters: bool
    notes: str = ""

    @property
    def expects_decline(self) -> bool:
        return self.category in DECLINE_CATEGORIES


def load_questions(path: Path) -> tuple[str, list[Question]]:
    if not path.is_file():
        raise EvalError(f"Question file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    dialect = data.get("dialect")
    if not dialect:
        raise EvalError(f"{path.name} needs a top-level 'dialect' saying which SQL the reference queries use.")

    questions, seen = [], set()
    for item in data.get("questions") or []:
        question = Question(
            id=str(item["id"]),
            category=item["category"],
            question=item["question"].strip(),
            reference_sql=(item.get("reference_sql") or "").strip() or None,
            order_matters=bool(item.get("order_matters", False)),
            notes=item.get("notes") or "",
        )
        if question.id in seen:
            raise EvalError(f"Duplicate question id {question.id} in {path.name}")
        if not question.expects_decline and not question.reference_sql:
            raise EvalError(f"Question {question.id} has no reference_sql")
        seen.add(question.id)
        questions.append(question)

    if not questions:
        raise EvalError(f"No questions in {path.name}")
    return dialect, questions


def select_questions(questions: list[Question], only: list[str] | None = None, category: str | None = None, limit: int | None = None) -> list[Question]:
    chosen = questions
    if only:
        wanted = set(only)
        unknown = wanted - {q.id for q in questions}
        if unknown:
            raise EvalError(f"Unknown question ids: {', '.join(sorted(unknown))}")
        chosen = [q for q in chosen if q.id in wanted]
    if category:
        chosen = [q for q in chosen if q.category == category]
    if limit:
        chosen = chosen[:limit]
    if not chosen:
        raise EvalError("No questions match those filters.")
    return chosen


def translate(sql: str, source_dialect: str, target_dialect: str) -> str:
    if source_dialect == target_dialect:
        return sql
    return sqlglot.transpile(sql, read=source_dialect, write=target_dialect)[0]


def result_path(model: str, pack: str, dialect: str, tag: str, today: date | None = None) -> Path:
    stamp = (today or date.today()).isoformat()
    name = "_".join(_slug(part) for part in (stamp, model, pack, dialect, tag) if part)
    path = RESULTS_DIR / f"{name}.jsonl"
    # never overwrite earlier evidence; a second run on the same day gets a suffix
    counter = 2
    while path.exists():
        path = RESULTS_DIR / f"{name}_{counter}.jsonl"
        counter += 1
    return path


def run_eval(askit: Askit, questions: list[Question], reference_dialect: str, out_path: Path, tag: str = "", questions_file: str = "", progress=print) -> list[dict]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dialect = askit.settings.db_dialect
    run = {
        "type": "run",
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": askit.settings.model,
        "pack": askit.pack.name,
        "dialect": dialect,
        "tag": tag,
        "sql_retries": askit.settings.sql_retries,
        "self_check": askit.settings.self_check,
        "check_model": (askit.settings.check_model or askit.settings.model) if askit.settings.self_check else None,
        "schema_retrieval": askit.settings.schema_retrieval,
        "schema_top_k": askit.settings.schema_top_k if askit.settings.schema_retrieval != "off" else None,
        "embedding_model": askit.settings.embedding_model if askit.settings.schema_retrieval in ("embedding", "hybrid") else None,
        "questions_file": questions_file,
        "question_count": len(questions),
    }

    records = []
    # written line by line so a crash or Ctrl+C keeps the questions already paid for
    with out_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps(run) + "\n")
        for number, question in enumerate(questions, 1):
            record = _evaluate_one(askit, question, reference_dialect, dialect)
            out.write(json.dumps(record) + "\n")
            out.flush()
            records.append(record)
            progress(f"[{number}/{len(questions)}] {question.id:<4} {question.category:<13} {record['outcome']:<9} {record['seconds']:.1f}s")
    return records


def _evaluate_one(askit: Askit, question: Question, reference_dialect: str, dialect: str) -> dict:
    record = {
        "type": "question",
        "id": question.id,
        "category": question.category,
        "question": question.question,
        "order_matters": question.order_matters,
        "expects_decline": question.expects_decline,
    }

    try:
        # no history: each question is judged on its own
        answer = askit.ask(question.question)
    except Exception as error:
        # one broken question must not end a paid-for run; the error is kept and scored as a failure
        message = str(error) if isinstance(error, (LLMError, DatabaseError)) else f"{type(error).__name__}: {error}"
        record.update(outcome="error", text="", sql=None, error=message, result=None, seconds=0.0, retries=0, schema_tables=[], self_check="", first_sql=None, first_result=None,
                      usage={"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0})
    else:
        record.update(
            outcome=answer.outcome,
            text=answer.text,
            sql=answer.sql,
            error=answer.error,
            result=_result_json(answer.result),
            seconds=round(answer.seconds, 2),
            retries=answer.retries,
            schema_tables=answer.tables,
            self_check=answer.self_check,
            check_error=answer.check_error,
            first_sql=answer.first_sql,
            first_result=_result_json(answer.first_result),
            check_usage={
                "input_tokens": answer.check_usage.input_tokens,
                "output_tokens": answer.check_usage.output_tokens,
                "cache_read_tokens": answer.check_usage.cache_read_tokens,
                "cache_write_tokens": answer.check_usage.cache_write_tokens,
            },
            usage={
                "calls": answer.usage.calls,
                "input_tokens": answer.usage.input_tokens,
                "output_tokens": answer.usage.output_tokens,
                "cache_read_tokens": answer.usage.cache_read_tokens,
                "cache_write_tokens": answer.usage.cache_write_tokens,
            },
        )

    record["reference"] = _run_reference(askit, question, reference_dialect, dialect)
    return record


def _run_reference(askit: Askit, question: Question, reference_dialect: str, dialect: str) -> dict | None:
    if not question.reference_sql:
        return None
    sql = translate(question.reference_sql, reference_dialect, dialect)
    # the reference runs on the same database as the answer, but skips the guardrails because we wrote it
    try:
        result = askit.db.run(sql)
    except DatabaseError as error:
        return {"sql": sql, "error": str(error), "result": None}
    return {"sql": sql, "error": None, "result": _result_json(result)}


def _result_json(result: QueryResult | None) -> dict | None:
    if result is None:
        return None
    rows = [[_json_value(row[column]) for column in result.columns] for row in result.rows[:STORED_ROWS]]
    return {
        "columns": result.columns,
        "rows": rows,
        "row_count": result.row_count,
        # truncated: the database had more rows than Askit fetches; rows_cut: more were fetched than this file keeps
        "truncated": result.truncated,
        "rows_cut": result.row_count > STORED_ROWS,
    }


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", text).strip("-").lower()

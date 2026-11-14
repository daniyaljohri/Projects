import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from askit.evaluate import EvalError
from askit.retrieval import reference_tables

# Decimals within this relative difference count as equal, so 6.77% rounded to 6.8% still passes
RELATIVE_TOLERANCE = 0.005
REFUSALS = ("declined", "blocked")
# stops a pathological result with many identical columns from trying every pairing
MAX_COLUMN_MAPPINGS = 2000

# USD per million tokens: input, output, cache read, cache write. List prices for prompts under 100K tokens,
# from platform.claude.com/docs/en/about-claude/pricing, November 2026. Cache writes are 1.25x input.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.40, 5.00),
}

RULES = """\
- Out-of-scope and adversarial questions pass when Askit declines or the guardrails block the query.
- Every other question passes only when the query runs and returns the same result as the reference query:
  - column names are ignored, and extra columns are allowed, but every reference column must appear;
  - the number of rows must be the same;
  - row order counts only for questions marked `order_matters`;
  - whole numbers must match exactly; decimals may differ by up to 0.5% (rounding);
  - a rate given as a fraction (0.0677) matches the same rate as a percentage (6.77);
  - text ignores case and surrounding spaces, and timestamps ignore `T` versus a space.
- A question whose reference query failed is left out of the accuracy and listed separately."""


@dataclass
class Score:
    id: str
    category: str
    question: str
    outcome: str
    passed: bool | None  # None when the reference itself failed and the question can't be judged
    reason: str = ""
    detail: str = ""


def load_run(path: Path) -> tuple[dict, list[dict]]:
    if not path.is_file():
        raise EvalError(f"Result file not found: {path}")
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0].get("type") != "run":
        raise EvalError(f"{path.name} is not an evaluation result file.")
    return lines[0], [line for line in lines[1:] if line.get("type") == "question"]


def score_record(record: dict) -> Score:
    score = Score(record["id"], record["category"], record["question"], record["outcome"], passed=False)
    outcome = record["outcome"]

    if record["expects_decline"]:
        if outcome in REFUSALS:
            score.passed = True
        elif outcome == "error":
            score.reason, score.detail = "error", record.get("error") or ""
        else:
            score.reason, score.detail = "should_decline", f"Askit {outcome} it"
        return score

    reference = record.get("reference") or {}
    if reference.get("error") or not reference.get("result"):
        score.passed = None
        score.reason, score.detail = "reference_error", reference.get("error") or "no reference result"
        return score

    if outcome != "answered":
        reasons = {"declined": "wrongly_declined", "blocked": "wrongly_blocked"}
        score.reason = reasons.get(outcome, "error")
        score.detail = record.get("error") or record.get("text") or ""
        return score

    matched, detail = compare_results(record["result"], reference["result"], record["order_matters"])
    score.passed = matched
    if not matched:
        score.reason, score.detail = "wrong_result", detail
    return score


def compare_results(answer: dict, reference: dict, order_matters: bool) -> tuple[bool, str]:
    if answer["row_count"] != reference["row_count"] or answer["truncated"] != reference["truncated"]:
        return False, f"{answer['row_count']} rows, expected {reference['row_count']}"
    if answer.get("rows_cut") or reference.get("rows_cut"):
        return False, "too many rows to compare"

    got = [[_normalise(v) for v in row] for row in answer["rows"]]
    want = [[_normalise(v) for v in row] for row in reference["rows"]]
    if not want:
        return True, ""
    width = len(want[0])

    candidates = []
    for ref_col in range(width):
        want_col = [row[ref_col] for row in want]
        options = [col for col in range(len(got[0]) if got else 0) if _column_matches([row[col] for row in got], want_col, order_matters)]
        if not options:
            return False, f"no column matches reference column {reference['columns'][ref_col]}"
        candidates.append(options)

    tried = 0
    for mapping in product(*candidates):
        if len(set(mapping)) < width:
            continue
        tried += 1
        if tried > MAX_COLUMN_MAPPINGS:
            break
        projected = [[row[col] for col in mapping] for row in got]
        if _rows_match(projected, want, order_matters):
            return True, ""
    return False, "values match column by column but not row by row" if tried else "two reference columns match only the same answer column"


def _column_matches(got: list, want: list, order_matters: bool) -> bool:
    if not order_matters:
        got, want = sorted(got, key=_sort_key), sorted(want, key=_sort_key)
    return all(_values_equal(g, w) for g, w in zip(got, want))


def _rows_match(got: list[list], want: list[list], order_matters: bool) -> bool:
    if order_matters:
        return all(_row_equal(g, w) for g, w in zip(got, want))
    unused = list(range(len(got)))
    for want_row in want:
        for position, index in enumerate(unused):
            if _row_equal(got[index], want_row):
                del unused[position]
                break
        else:
            return False
    return True


def _row_equal(got: list, want: list) -> bool:
    return all(_values_equal(g, w) for g, w in zip(got, want))


def _values_equal(got, want) -> bool:
    if isinstance(want, float) and isinstance(got, float):
        if want.is_integer() and got.is_integer():
            return got == want
        return _close(got, want) or _close(got * 100, want) or _close(got, want * 100)
    return got == want


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=RELATIVE_TOLERANCE, abs_tol=1e-9)


TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.0+)?$")


def _normalise(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    match = TIMESTAMP.match(text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return text.lower()


def _sort_key(value):
    # None, numbers and text sort in separate groups so mixed columns never compare across types
    if value is None:
        return (0, 0.0, "")
    if isinstance(value, float):
        return (1, value, "")
    return (2, 0.0, value)


def estimate_cost(model: str, tokens: dict) -> float | None:
    prices = PRICES.get(model)
    if not prices:
        return None
    input_price, output_price, read_price, write_price = prices
    return (
        tokens["input_tokens"] * input_price
        + tokens["output_tokens"] * output_price
        + tokens["cache_read_tokens"] * read_price
        + tokens.get("cache_write_tokens", 0) * write_price
    ) / 1_000_000


def summarise(run: dict, records: list[dict]) -> str:
    scores = [score_record(record) for record in records]
    judged = [s for s in scores if s.passed is not None]
    passed = sum(1 for s in judged if s.passed)

    token_keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    tokens = {key: sum(r["usage"].get(key, 0) for r in records) for key in token_keys}
    seconds = [r["seconds"] for r in records]
    cost = estimate_cost(run["model"], tokens)

    lines = [
        f"# Evaluation: {run['pack']} pack, {run['model']}, {run['dialect']}" + (f" ({run['tag']})" if run.get("tag") else ""),
        "",
        f"Run started {run['started']} with {len(records)} questions from `{run.get('questions_file', '')}`.",
        "",
        f"**Accuracy: {passed} of {len(judged)} ({_pct(passed, len(judged))})**",
        "",
        "| Category | Questions | Passed | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for category in _categories(scores):
        group = [s for s in judged if s.category == category]
        ok = sum(1 for s in group if s.passed)
        lines.append(f"| {category} | {len(group)} | {ok} | {_pct(ok, len(group))} |")

    outcomes = Counter(s.outcome for s in scores)
    retried = [(r, s) for r, s in zip(records, scores) if r.get("retries", 0)]
    rescued = sum(1 for _, s in retried if s.passed)
    lines += [
        "",
        "## Cost and speed",
        "",
        f"- Outcomes: " + ", ".join(f"{name} {count}" for name, count in sorted(outcomes.items())),
        f"- Response time: {sum(seconds) / len(seconds):.1f}s average, {max(seconds):.1f}s slowest, {sum(seconds):.0f}s total",
        f"- Retries after a failed query (up to {run.get('sql_retries', 0)} per question): {len(retried)} questions retried, {rescued} of them then passed",
        _retrieval_line(run, records),
        f"- Tokens: {tokens['input_tokens']:,} input, {tokens['output_tokens']:,} output, "
        f"{tokens['cache_read_tokens']:,} read from cache, {tokens['cache_write_tokens']:,} written to cache",
        "- Estimated cost: " + (f"${cost:.4f} (${cost / len(records):.5f} per question), list prices" if cost is not None else f"no price listed for {run['model']}"),
    ]

    failures = [s for s in scores if s.passed is False]
    lines += ["", "## Failures", ""]
    if failures:
        lines += ["| Id | Category | Reason | Detail | Question |", "|---|---|---|---|---|"]
        for s in failures:
            lines.append(f"| {s.id} | {s.category} | {s.reason} | {_cell(s.detail)} | {_cell(s.question)} |")
    else:
        lines.append("None.")

    unjudged = [s for s in scores if s.passed is None]
    if unjudged:
        lines += ["", "## Not scored (reference query failed)", ""]
        lines += [f"- {s.id}: {_cell(s.detail)}" for s in unjudged]

    lines += ["", "## Scoring rules", "", RULES, ""]
    return "\n".join(lines)


def _retrieval_line(run: dict, records: list[dict]) -> str:
    method = run.get("schema_retrieval") or "off"
    if method == "off":
        return "- Schema retrieval: off (every table sent)"
    covered = total = 0
    for record in records:
        reference = record.get("reference") or {}
        if not reference.get("sql") or not record.get("schema_tables"):
            continue
        total += 1
        sent = {name.lower() for name in record["schema_tables"]}
        if reference_tables(reference["sql"], run["dialect"]) <= sent:
            covered += 1
    model = f", {run['embedding_model']}" if run.get("embedding_model") else ""
    return (f"- Schema retrieval: {method}{model}, top {run.get('schema_top_k')} tables; "
            f"every table the reference query needs was sent for {covered} of {total} questions")


def write_summary(results_path: Path) -> Path:
    run, records = load_run(results_path)
    if not records:
        raise EvalError(f"{results_path.name} has no question results.")
    summary_path = results_path.with_suffix(".md")
    summary_path.write_text(summarise(run, records), encoding="utf-8")
    return summary_path


def _categories(scores: list[Score]) -> list[str]:
    return list(dict.fromkeys(s.category for s in scores))


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def _cell(text: str, limit: int = 120) -> str:
    text = " ".join(str(text).split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"

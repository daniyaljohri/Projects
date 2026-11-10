import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import anthropic

from askit.config import ConfigError, Settings
from askit.db import QueryResult

SQL_MAX_TOKENS = 1024
NARRATION_MAX_TOKENS = 400
NARRATION_PREVIEW_ROWS = 50
# columns that hold labels, not quantities, so 2016 stays 2016 and not 2,016
PLAIN_NUMBER_COLUMNS = re.compile(r"(year|month|quarter|week|day|_id|_key|zip|code)$", re.IGNORECASE)

TOOLS = [
    {
        "name": "run_query",
        "description": "Run one read-only SELECT query that answers the question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The SQL query, with no explanation around it."},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "decline",
        "description": "Use when the question cannot be answered from the tables, or asks for anything other than reading data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "One sentence for the user explaining why."},
            },
            "required": ["reason"],
        },
    },
]

NARRATION_PROMPT = """You explain query results to a business user in plain English.

- Answer the question in one to three sentences, using the numbers in the results.
- Never invent, estimate or calculate numbers that are not in the results.
- Do not repeat the table; it is shown to the user separately.
- Do not mention SQL, queries, tables or databases.
- Write plain text, without markdown.
- If there are no rows, say that nothing matched, in one sentence.
- If only some rows are shown, base the answer on those and don't guess about the rest."""


class LLMError(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    calls: int = 0
    seconds: float = 0.0

    def add(self, response, seconds: float) -> None:
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        self.cache_read_tokens += response.usage.cache_read_input_tokens or 0
        self.calls += 1
        self.seconds += seconds


@dataclass
class SqlDecision:
    sql: str | None = None
    decline_reason: str | None = None
    usage: Usage = field(default_factory=Usage)


class LLM:
    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise ConfigError("ANTHROPIC_API_KEY is not set. Add it to .env.")
        self.model = settings.model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _call(self, usage: Usage, **kwargs):
        started = time.perf_counter()
        try:
            response = self.client.messages.create(model=self.model, **kwargs)
        except anthropic.APIError as error:
            raise LLMError(f"Claude API error: {error}") from error
        usage.add(response, time.perf_counter() - started)
        return response

    def generate_sql(self, question: str, system_prompt: str, history: list[dict] | None = None) -> SqlDecision:
        decision = SqlDecision()
        response = self._call(
            decision.usage,
            max_tokens=SQL_MAX_TOKENS,
            # the system prompt is identical on every call, so cache it
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            tool_choice={"type": "any"},
            messages=[*(history or []), {"role": "user", "content": question}],
        )

        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "run_query" and block.input.get("sql", "").strip():
                decision.sql = block.input["sql"].strip()
                return decision
            if block.name == "decline":
                decision.decline_reason = block.input.get("reason", "").strip() or "I can't answer that from this data."
                return decision

        raise LLMError("Claude did not return a query or a reason to decline.")

    def narrate(self, question: str, result: QueryResult, usage: Usage) -> str:
        response = self._call(
            usage,
            max_tokens=NARRATION_MAX_TOKENS,
            system=NARRATION_PROMPT,
            messages=[{"role": "user", "content": _narration_message(question, result)}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()


def _narration_message(question: str, result: QueryResult) -> str:
    shown = result.rows[:NARRATION_PREVIEW_ROWS]
    lines = [f"Question: {question}", ""]

    if not result.rows:
        lines.append("Results: no rows.")
        return "\n".join(lines)

    total = f"more than {result.row_count:,}" if result.truncated else f"{result.row_count:,}"
    if len(shown) == result.row_count and not result.truncated:
        lines.append(f"Results (all {total} rows):")
    else:
        lines.append(f"Results ({total} rows in total, first {len(shown)} shown):")
    lines.append(" | ".join(result.columns))
    for row in shown:
        lines.append(" | ".join(format_value(row[column], column) for column in result.columns))
    return "\n".join(lines)


def format_value(value, column: str = "") -> str:
    if value is None:
        return ""
    if isinstance(value, (float, Decimal)):
        number = float(value)
        if abs(number) >= 100:
            return f"{number:,.2f}"
        return f"{int(number)}" if number.is_integer() else f"{number:.4g}"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M") if value.time() != datetime.min.time() else value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value) if PLAIN_NUMBER_COLUMNS.search(column) else f"{value:,}"
    return str(value)

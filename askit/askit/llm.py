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


FIX_PROMPT = """That query could not run. The error was:
{error}

Write a corrected query for my question, or decline if it can't be answered from these tables."""


CHECK_PROMPT = """That query ran. This is what it returned:
{preview}

Check the result against my question before it is shown to me:
- Does it cover exactly the period, filters and groups I asked for, no more and no less?
- If I asked for one thing ("which", "the top", "the highest"), is it one row; if I asked for a list or top N, is it that many?
- Is every number calculated at the level the business rules and table grain require?
- Do the columns answer the question?

If the result answers my question, call accept_result. If not, call run_query with a corrected query."""

ACCEPT_TOOL = {
    "name": "accept_result",
    "description": "Use when the query result already answers the question correctly.",
    "input_schema": {"type": "object", "properties": {}},
}


class LLMError(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0
    seconds: float = 0.0

    def add(self, response, seconds: float) -> None:
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        self.cache_read_tokens += response.usage.cache_read_input_tokens or 0
        self.cache_write_tokens += getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        self.calls += 1
        self.seconds += seconds

    def merge(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.calls += other.calls
        self.seconds += other.seconds


@dataclass
class SqlDecision:
    sql: str | None = None
    decline_reason: str | None = None
    accepted: bool = False
    usage: Usage = field(default_factory=Usage)


class LLM:
    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise ConfigError("ANTHROPIC_API_KEY is not set. Add it to .env.")
        self.model = settings.model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        # some models refuse a forced tool call; after the first refusal every call asks with "auto" instead
        self.forced_tools = True

    def _call(self, usage: Usage, **kwargs):
        started = time.perf_counter()
        if not self.forced_tools and "tool_choice" in kwargs:
            kwargs["tool_choice"] = {"type": "auto"}
        try:
            response = self.client.messages.create(model=self.model, **kwargs)
        except anthropic.BadRequestError as error:
            if "tool_choice" not in str(error) or not self.forced_tools or "tool_choice" not in kwargs:
                raise LLMError(f"Claude API error: {error}") from error
            # the prompt still asks for a tool call; a reply without one is caught by the caller
            self.forced_tools = False
            return self._call(usage, **kwargs)
        except anthropic.APIError as error:
            raise LLMError(f"Claude API error: {error}") from error
        usage.add(response, time.perf_counter() - started)
        return response

    def generate_sql(self, question: str, system_prompt: str | list[str], history: list[dict] | None = None) -> SqlDecision:
        return self._decide(system_prompt, [*(history or []), {"role": "user", "content": question}])

    def fix_sql(self, question: str, system_prompt: str | list[str], history: list[dict] | None, sql: str, error: str) -> SqlDecision:
        # the same conversation plus the failed attempt, the way you'd read an error in SSMS and fix the line
        messages = [
            *(history or []),
            {"role": "user", "content": question},
            {"role": "assistant", "content": f"SQL I wrote:\n{sql}"},
            {"role": "user", "content": FIX_PROMPT.format(error=error)},
        ]
        return self._decide(system_prompt, messages)

    def check_result(self, question: str, system_prompt: str | list[str], history: list[dict] | None, sql: str, result: QueryResult) -> SqlDecision:
        # a second look at the answer's shape, like checking a report against the request before sending it
        messages = [
            *(history or []),
            {"role": "user", "content": question},
            {"role": "assistant", "content": f"SQL I wrote:\n{sql}"},
            {"role": "user", "content": CHECK_PROMPT.format(preview=_result_preview(result))},
        ]
        return self._decide(system_prompt, messages, tools=[ACCEPT_TOOL, TOOLS[0]])

    def _decide(self, system_prompt: str | list[str], messages: list[dict], tools: list[dict] = TOOLS) -> SqlDecision:
        parts = [system_prompt] if isinstance(system_prompt, str) else system_prompt
        # the first part is the same on every call, so cache it; later parts (tables picked per question) change
        system = [{"type": "text", "text": parts[0], "cache_control": {"type": "ephemeral"}}]
        system += [{"type": "text", "text": part} for part in parts[1:]]
        decision = SqlDecision()
        response = self._call(
            decision.usage,
            max_tokens=SQL_MAX_TOKENS,
            system=system,
            tools=tools,
            tool_choice={"type": "any"},
            messages=messages,
        )

        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "run_query" and block.input.get("sql", "").strip():
                decision.sql = block.input["sql"].strip()
                return decision
            if block.name == "accept_result":
                decision.accepted = True
                return decision
            if block.name == "decline":
                decision.decline_reason = block.input.get("reason", "").strip() or "I can't answer that from this data."
                return decision

        raise LLMError("Claude did not return a query or a reason to decline.")

    def call_tool(self, system: str, message: str, tool: dict, usage: Usage, max_tokens: int) -> dict:
        response = self._call(
            usage,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": message}],
        )
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude's reply was cut off at the token limit. Try fewer tables at a time.")
        for block in response.content:
            if block.type == "tool_use":
                return block.input
        raise LLMError(f"Claude did not call {tool['name']}.")

    def narrate(self, question: str, result: QueryResult, usage: Usage) -> str:
        response = self._call(
            usage,
            max_tokens=NARRATION_MAX_TOKENS,
            system=NARRATION_PROMPT,
            messages=[{"role": "user", "content": _narration_message(question, result)}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()


def _result_preview(result: QueryResult, rows: int = 10) -> str:
    total = f"more than {result.row_count:,}" if result.truncated else f"{result.row_count:,}"
    lines = [f"{total} rows. Columns: {', '.join(result.columns)}"]
    for row in result.rows[:rows]:
        lines.append(" | ".join(format_value(row[column], column) for column in result.columns))
    if result.row_count > rows:
        lines.append(f"... first {rows} rows shown")
    return "\n".join(lines)


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

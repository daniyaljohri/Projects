import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from askit.config import PROJECT_ROOT, Settings
from askit.db import Database, DatabaseError, QueryResult
from askit.guardrails import GuardrailError, check_sql
from askit.llm import LLM, Usage
from askit.pack import load_pack
from askit.prompt import build_prompt_parts, build_system_prompt, tables_section
from askit.retrieval import SchemaRetriever

LOG_PATH = PROJECT_ROOT / "logs" / "queries.jsonl"
HISTORY_TURNS = 3


@dataclass
class Answer:
    question: str
    outcome: str  # answered, declined, blocked or failed
    text: str
    sql: str | None = None
    result: QueryResult | None = None
    error: str | None = None
    usage: Usage = field(default_factory=Usage)
    seconds: float = 0.0
    retries: int = 0
    # tables sent to Claude when schema retrieval is on; empty means every table was sent
    tables: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


class Askit:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pack = load_pack(settings.pack_dir)
        self.db = Database.from_settings(settings, self.pack.schemas)
        self.llm = LLM(settings)
        self.system_prompt = build_system_prompt(self.pack, settings.db_dialect)
        self.retriever = None
        if settings.schema_retrieval != "off":
            self.retriever = SchemaRetriever.build(self.pack, settings.schema_retrieval, settings.schema_top_k, model=settings.embedding_model)
            self.prompt_head, self.table_texts = build_prompt_parts(self.pack, settings.db_dialect)

    def _system_for(self, question: str, history: list["Answer"]) -> tuple[str | list[str], list[str]]:
        if not self.retriever:
            return self.system_prompt, []
        # earlier questions are included so a follow-up like "now by state" keeps the tables it needs
        query = " ".join([previous.question for previous in history[-HISTORY_TURNS:]] + [question])
        tables = self.retriever.retrieve(query)
        return [self.prompt_head, tables_section(self.table_texts[name] for name in tables)], tables

    def ask(self, question: str, history: list[Answer] | None = None) -> Answer:
        started = time.perf_counter()
        answer = self._answer(question.strip(), history or [])
        answer.seconds = time.perf_counter() - started
        self._log(answer)
        return answer

    def _answer(self, question: str, history: list[Answer]) -> Answer:
        messages = _history_messages(history)
        system, tables = self._system_for(question, history)
        decision = self.llm.generate_sql(question, system, messages)
        usage = decision.usage
        retries = 0

        while True:
            if decision.decline_reason:
                return Answer(question, "declined", decision.decline_reason, usage=usage, retries=retries, tables=tables)

            try:
                checked = check_sql(decision.sql, self.settings.db_dialect, self.pack.allowed_tables)
            except GuardrailError as error:
                failure = Answer(question, "blocked", f"I couldn't run that query safely: {error}", sql=decision.sql, error=str(error), usage=usage, retries=retries, tables=tables)
                retryable = error.retryable
            else:
                try:
                    result = self.db.run(checked.sql)
                except DatabaseError as error:
                    failure = Answer(question, "failed", "The query failed when it ran. Try rephrasing the question.", sql=checked.sql, error=str(error), usage=usage, retries=retries, tables=tables)
                    retryable = error.retryable
                else:
                    text = self.llm.narrate(question, result, usage)
                    return Answer(question, "answered", text, sql=checked.sql, result=result, usage=usage, retries=retries, tables=tables)

            # a safety block is final: sending it back would teach the model how to get round the guardrails
            if not retryable or retries >= self.settings.sql_retries:
                return failure
            retries += 1
            decision = self.llm.fix_sql(question, system, messages, failure.sql, failure.error)
            usage.merge(decision.usage)

    def _log(self, answer: Answer) -> None:
        LOG_PATH.parent.mkdir(exist_ok=True)
        record = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "id": answer.id,
            "pack": self.pack.name,
            "model": self.settings.model,
            "question": answer.question,
            "outcome": answer.outcome,
            "sql": answer.sql,
            "rows": answer.result.row_count if answer.result else None,
            "error": answer.error,
            "retries": answer.retries,
            "tables": answer.tables,
            "input_tokens": answer.usage.input_tokens,
            "output_tokens": answer.usage.output_tokens,
            "cache_read_tokens": answer.usage.cache_read_tokens,
            "seconds": round(answer.seconds, 2),
        }
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")


def _history_messages(history: list[Answer]) -> list[dict]:
    # earlier questions and the SQL that answered them, so follow-ups like "now by state" work
    messages = []
    for previous in history[-HISTORY_TURNS:]:
        reply = f"SQL used:\n{previous.sql}" if previous.sql else previous.text
        messages.append({"role": "user", "content": previous.question})
        messages.append({"role": "assistant", "content": reply})
    return messages

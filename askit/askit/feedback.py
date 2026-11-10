import json
from datetime import datetime, timezone
from pathlib import Path

from askit.config import PROJECT_ROOT

FEEDBACK_LOG = PROJECT_ROOT / "logs" / "feedback.jsonl"


def record_feedback(path: Path, *, answer, pack: str, model: str, rating: str, comment: str = "") -> dict:
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "answer_id": answer.id,
        "pack": pack,
        "model": model,
        "rating": rating,
        "comment": comment.strip(),
        "question": answer.question,
        "outcome": answer.outcome,
        "sql": answer.sql,
        "rows": answer.result.row_count if answer.result else None,
    }
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")
    return record

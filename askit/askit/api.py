from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from askit import feedback
from askit.config import ConfigError, get_settings
from askit.db import DatabaseError
from askit.export import build_workbook, filename_for
from askit.llm import LLMError
from askit.pack import PackError
from askit.pipeline import Answer, Askit

DISPLAY_ROWS = 100
SESSION_TURNS = 10

app = FastAPI(title="Askit", description="Ask questions about a database in plain English.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(ConfigError)
@app.exception_handler(PackError)
async def setup_error(_request: Request, error: Exception):
    return JSONResponse(status_code=500, content={"detail": f"Setup problem: {error}"})


_askit: Askit | None = None
sessions: dict[str, list[Answer]] = {}


def get_askit() -> Askit:
    global _askit
    if _askit is None:
        _askit = Askit(get_settings())
    return _askit


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: str = Field(default="default", max_length=100)


class FeedbackRequest(BaseModel):
    session_id: str = Field(max_length=100)
    answer_id: str = Field(max_length=64)
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=1000)


class ExportRequest(BaseModel):
    session_id: str = Field(default="default", max_length=100)
    answer_id: str | None = Field(default=None, max_length=64)


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _answer_json(answer: Answer) -> dict:
    result = answer.result
    rows = []
    if result:
        rows = [{c: _json_value(row[c]) for c in result.columns} for row in result.rows[:DISPLAY_ROWS]]
    return {
        "id": answer.id,
        "outcome": answer.outcome,
        "answer": answer.text,
        "sql": answer.sql,
        "columns": result.columns if result else [],
        "rows": rows,
        "row_count": result.row_count if result else 0,
        "truncated": result.truncated if result else False,
        "error": answer.error,
        "retries": answer.retries,
        "seconds": round(answer.seconds, 2),
    }


@app.get("/health")
def health():
    settings = get_settings()
    return {"status": "ok", "pack": settings.pack, "model": settings.model, "dialect": settings.db_dialect}


@app.get("/pack")
def pack_info():
    pack = get_askit().pack
    return {"name": pack.name, "display_name": pack.display_name, "suggested_questions": pack.suggested_questions}


# async def with no awaits on purpose: the request runs on the main thread,
# because pyodbc with Windows authentication hung when called from a worker thread in v1
@app.post("/chat")
async def chat(request: ChatRequest):
    history = sessions.setdefault(request.session_id, [])
    try:
        answer = get_askit().ask(request.question, history)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except DatabaseError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    history.append(answer)
    del history[:-SESSION_TURNS]
    return _answer_json(answer)


@app.post("/export")
async def export(request: ExportRequest):
    history = sessions.get(request.session_id, [])
    candidates = [a for a in history if a.result and a.result.rows]
    if request.answer_id:
        candidates = [a for a in candidates if a.id == request.answer_id]
    if not candidates:
        raise HTTPException(status_code=404, detail="There are no results to export for this answer.")

    answer = candidates[-1]
    content = build_workbook(answer.result, answer.question, answer.sql)
    filename = filename_for(answer.question)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/feedback")
async def give_feedback(request: FeedbackRequest):
    answer = next((a for a in sessions.get(request.session_id, []) if a.id == request.answer_id), None)
    if answer is None:
        raise HTTPException(status_code=404, detail="That answer is no longer in this session.")

    askit = get_askit()
    feedback.record_feedback(
        feedback.FEEDBACK_LOG,
        answer=answer,
        pack=askit.pack.name,
        model=askit.settings.model,
        rating=request.rating,
        comment=request.comment,
    )
    return {"saved": True}


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    sessions.pop(session_id, None)
    return {"cleared": session_id}

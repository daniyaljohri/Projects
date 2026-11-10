import json
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import askit.api as api
import askit.feedback as feedback
from askit.db import QueryResult
from askit.pipeline import Answer

RESULT = QueryResult(
    columns=["order_year", "total_revenue_brl", "first_order"],
    rows=[{"order_year": 2017, "total_revenue_brl": Decimal("7142672.43"), "first_order": datetime(2017, 1, 5, 12, 0)}],
    truncated=False,
)


class FakeAskit:
    def __init__(self):
        self.calls = []
        self.pack = type("P", (), {"name": "olist", "display_name": "Olist", "suggested_questions": ["Q1"]})()
        self.settings = type("S", (), {"model": "test-model"})()

    def ask(self, question, history=None):
        self.calls.append((question, list(history or [])))
        if "employees" in question:
            return Answer(question, "declined", "No employee data.")
        return Answer(question, "answered", "Revenue was R$7.1M.", sql="SELECT 1", result=RESULT)


@pytest.fixture
def client(monkeypatch, tmp_path):
    fake = FakeAskit()
    monkeypatch.setattr(api, "_askit", fake)
    monkeypatch.setattr(api, "sessions", {})
    monkeypatch.setattr(feedback, "FEEDBACK_LOG", tmp_path / "feedback.jsonl")
    return TestClient(api.app), fake


def test_chat_returns_json_safe_rows(client):
    http, _ = client
    body = http.post("/chat", json={"question": "Revenue by year", "session_id": "s1"}).json()

    assert body["outcome"] == "answered"
    assert body["columns"] == ["order_year", "total_revenue_brl", "first_order"]
    assert body["rows"] == [{"order_year": 2017, "total_revenue_brl": 7142672.43, "first_order": "2017-01-05T12:00:00"}]
    assert body["row_count"] == 1


def test_follow_ups_share_session_history(client):
    http, fake = client
    http.post("/chat", json={"question": "Revenue by year", "session_id": "s1"})
    http.post("/chat", json={"question": "now for SP", "session_id": "s1"})
    http.post("/chat", json={"question": "Revenue by year", "session_id": "s2"})

    assert len(fake.calls[1][1]) == 1
    assert fake.calls[2][1] == []


def test_export_uses_the_last_result(client):
    http, _ = client
    http.post("/chat", json={"question": "Revenue by year", "session_id": "s1"})
    http.post("/chat", json={"question": "How many employees?", "session_id": "s1"})

    response = http.post("/export", json={"session_id": "s1"})
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="revenue_by_year.xlsx"'
    assert response.content[:2] == b"PK"


def test_export_picks_the_requested_answer(client):
    http, _ = client
    first = http.post("/chat", json={"question": "Revenue by year", "session_id": "s1"}).json()
    http.post("/chat", json={"question": "Revenue for SP", "session_id": "s1"})

    response = http.post("/export", json={"session_id": "s1", "answer_id": first["id"]})
    assert response.headers["content-disposition"] == 'attachment; filename="revenue_by_year.xlsx"'
    assert http.post("/export", json={"session_id": "s1", "answer_id": "unknown"}).status_code == 404


def test_export_without_results(client):
    http, _ = client
    assert http.post("/export", json={"session_id": "new"}).status_code == 404


def test_empty_question_is_rejected(client):
    http, _ = client
    assert http.post("/chat", json={"question": ""}).status_code == 422


def test_pack_info(client):
    http, _ = client
    assert http.get("/pack").json()["suggested_questions"] == ["Q1"]


def test_feedback_is_saved_with_the_question_and_sql(client):
    http, _ = client
    answer = http.post("/chat", json={"question": "Revenue by year", "session_id": "s1"}).json()

    response = http.post("/feedback", json={"session_id": "s1", "answer_id": answer["id"], "rating": "down", "comment": "wrong year"})
    assert response.json() == {"saved": True}

    record = json.loads(feedback.FEEDBACK_LOG.read_text().splitlines()[0])
    assert record["rating"] == "down"
    assert record["comment"] == "wrong year"
    assert record["sql"] == "SELECT 1"
    assert record["model"] == "test-model"


def test_feedback_validation(client):
    http, _ = client
    answer = http.post("/chat", json={"question": "Revenue by year", "session_id": "s1"}).json()
    assert http.post("/feedback", json={"session_id": "s1", "answer_id": answer["id"], "rating": "meh"}).status_code == 422
    assert http.post("/feedback", json={"session_id": "s1", "answer_id": "nope", "rating": "up"}).status_code == 404

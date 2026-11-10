from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import askit.api as api
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

    def ask(self, question, history=None):
        self.calls.append((question, list(history or [])))
        if "employees" in question:
            return Answer(question, "declined", "No employee data.")
        return Answer(question, "answered", "Revenue was R$7.1M.", sql="SELECT 1", result=RESULT)


@pytest.fixture
def client(monkeypatch):
    fake = FakeAskit()
    monkeypatch.setattr(api, "_askit", fake)
    monkeypatch.setattr(api, "sessions", {})
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


def test_export_without_results(client):
    http, _ = client
    assert http.post("/export", json={"session_id": "new"}).status_code == 404


def test_empty_question_is_rejected(client):
    http, _ = client
    assert http.post("/chat", json={"question": ""}).status_code == 422


def test_pack_info(client):
    http, _ = client
    assert http.get("/pack").json()["suggested_questions"] == ["Q1"]

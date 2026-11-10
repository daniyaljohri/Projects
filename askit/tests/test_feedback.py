import json

from askit.feedback import popular_questions


def write(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def asked(question, outcome="answered", pack="olist"):
    return {"question": question, "outcome": outcome, "pack": pack}


def test_popular_counts_answered_questions_only(tmp_path):
    queries, ratings = tmp_path / "q.jsonl", tmp_path / "f.jsonl"
    write(queries, [
        asked("Revenue by state?"),
        asked("Revenue by state?"),
        asked("revenue  by STATE"),
        asked("Top categories"),
        asked("Top categories"),
        asked("Delete everything", outcome="declined"),
        asked("Delete everything", outcome="declined"),
        asked("Asked once"),
    ])

    result = popular_questions(queries, ratings, pack="olist", exclude=[])

    assert result == [
        {"question": "Revenue by state?", "times_asked": 3},
        {"question": "Top categories", "times_asked": 2},
    ]


def test_popular_skips_suggested_other_packs_and_downvoted(tmp_path):
    queries, ratings = tmp_path / "q.jsonl", tmp_path / "f.jsonl"
    write(queries, [asked("Top sellers")] * 2 + [asked("Bad answer")] * 3 + [asked("Other pack", pack="shop")] * 3 + [asked("Good one")] * 2)
    write(ratings, [
        {"question": "Bad answer", "rating": "up", "pack": "olist"},
        {"question": "bad answer?", "rating": "down", "pack": "olist"},
    ])

    result = popular_questions(queries, ratings, pack="olist", exclude=["Top sellers?"])

    assert [r["question"] for r in result] == ["Good one"]


def test_popular_with_no_logs_yet(tmp_path):
    assert popular_questions(tmp_path / "none.jsonl", tmp_path / "none2.jsonl", pack="olist", exclude=[]) == []

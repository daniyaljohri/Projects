import json
from pathlib import Path

import numpy as np
import pytest

from askit.config import ConfigError
from askit.evaluate import load_questions
from askit.pack import Column, Table, load_pack
from askit.retrieval import (
    EmbeddingIndex,
    KeywordIndex,
    SchemaRetriever,
    fuse,
    rank,
    reference_tables,
    schema_recall,
    tokenize,
)

OLIST = load_pack(Path(__file__).resolve().parent.parent / "packs" / "olist")
QUESTIONS = Path(__file__).resolve().parent.parent / "packs" / "olist" / "eval" / "questions.yaml"
SYNONYMS = {"shop": "seller", "store": "seller", "buyer": "customer", "spend": "revenue", "left": "churn"}


class FakeEmbedder:
    """Bag of words with a few synonyms, so 'shops' lands near 'seller' the way a real model would."""

    model_name = "fake"

    def __init__(self):
        self.vocabulary = {}
        self.passage_calls = 0

    def _vector(self, text):
        vector = np.zeros(512, dtype="float32")
        for word in tokenize(text):
            word = SYNONYMS.get(word, word)
            index = self.vocabulary.setdefault(word, len(self.vocabulary) % 512)
            vector[index] += 1
        return vector

    def embed_passages(self, texts):
        self.passage_calls += 1
        return np.array([self._vector(t) for t in texts])

    def embed_query(self, text):
        return self._vector(text)


def test_tokenize_splits_names_and_plurals():
    assert tokenize("Which sellers have the highest late_delivery_rate_pct?") == ["seller", "highest", "late", "delivery", "rate", "pct"]
    assert tokenize("product categories") == ["product", "category"]


def test_keyword_finds_the_seller_summary():
    retriever = SchemaRetriever.build(OLIST, "keyword", 1)
    assert retriever.retrieve("Which seller tier has the most cancelled orders?") == ["chatbot.v_seller_summary"]


def test_wide_fact_table_is_not_buried():
    retriever = SchemaRetriever.build(OLIST, "keyword", 3)
    assert "chatbot.v_orders_full" in retriever.retrieve("What share of revenue came from orders paid by boleto?")


def test_keyword_scores_zero_without_shared_words():
    index = KeywordIndex(OLIST.tables)
    assert set(index.scores("zebra").values()) == {0.0}


def test_rank_keeps_pack_order_on_ties():
    assert rank({"a": 0.0, "b": 1.0, "c": 0.0}, ["a", "b", "c"]) == ["b", "a", "c"]


def test_fusion_rewards_tables_high_in_either_ranking():
    fused = fuse([["a", "b", "c", "d"], ["d", "b", "a", "c"]])
    assert fused[0] == "b" or fused[0] == "a"
    assert fused[-1] == "c"


def test_embedding_matches_meaning_not_words(tmp_path):
    retriever = SchemaRetriever.build(OLIST, "embedding", 1, embedder=FakeEmbedder(), cache_dir=tmp_path)
    assert retriever.retrieve("Which shops are in Curitiba?") == ["chatbot.v_seller_summary"]


def test_hybrid_combines_both(tmp_path):
    retriever = SchemaRetriever.build(OLIST, "hybrid", 2, embedder=FakeEmbedder(), cache_dir=tmp_path)
    assert retriever.keyword and retriever.embedding
    assert "chatbot.v_seller_summary" in retriever.retrieve("Which shops have the worst seller tier?")


def test_embeddings_are_cached_on_disk(tmp_path):
    first = FakeEmbedder()
    EmbeddingIndex(OLIST.tables, first, tmp_path)
    second = FakeEmbedder()
    EmbeddingIndex(OLIST.tables, second, tmp_path)
    assert first.passage_calls == 1 and second.passage_calls == 0
    assert len(list(tmp_path.glob("schema-*.npy"))) == 1


def test_editing_the_pack_re_embeds(tmp_path):
    EmbeddingIndex(OLIST.tables, FakeEmbedder(), tmp_path)
    changed = OLIST.tables[:1] + [Table("x.t", "one row", "new", [Column("c", "d")])]
    EmbeddingIndex(changed, FakeEmbedder(), tmp_path)
    assert len(list(tmp_path.glob("schema-*.npy"))) == 2


def test_unknown_method_is_rejected():
    with pytest.raises(ConfigError, match="keyword"):
        SchemaRetriever.build(OLIST, "magic", 3)


def test_reference_tables_skip_ctes():
    sql = """WITH ranked AS (SELECT seller_id FROM chatbot.v_seller_summary)
             SELECT o.order_id FROM chatbot.v_orders_full AS o JOIN ranked AS r ON r.seller_id = o.seller_id"""
    assert reference_tables(sql, "tsql") == {"chatbot.v_seller_summary", "chatbot.v_orders_full"}


def test_schema_recall_counts_misses():
    retriever = SchemaRetriever.build(OLIST, "keyword", 1)
    cases = [("q1", "Which seller tier is most common?", {"chatbot.v_seller_summary"}),
             ("q2", "Which seller tier is most common?", {"chatbot.v_monthly_trends"})]
    hits, misses = schema_recall(retriever, cases, 1)
    assert hits == 1 and misses[0][0] == "q2"


def test_keyword_recall_on_the_olist_questions():
    dialect, questions = load_questions(QUESTIONS)
    cases = [(q.id, q.question, reference_tables(q.reference_sql, dialect)) for q in questions if q.reference_sql]
    retriever = SchemaRetriever.build(OLIST, "keyword", 5)
    # with every table sent nothing can be missed; this guards the recall maths itself
    assert schema_recall(retriever, cases, 5)[0] == len(cases)


def test_retrieval_check_command_runs_without_api_key_or_database(monkeypatch, capsys):
    from askit.cli import main

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["retrieval-check", "--pack", "olist", "--methods", "keyword"]) == 0
    out = capsys.readouterr().out
    assert "keyword" in out and "top 3" in out and "Missed at top 3" in out

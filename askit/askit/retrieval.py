import hashlib
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp

from askit.config import PROJECT_ROOT, SCHEMA_RETRIEVAL_METHODS, ConfigError
from askit.pack import Pack, Table

METHODS = SCHEMA_RETRIEVAL_METHODS
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
INDEX_DIR = PROJECT_ROOT / "index"
# k1 limits how much repeating a word helps (standard value). b is how much long documents are penalised:
# 0.75 suits prose, but a table's text is long because it has many columns, not because it rambles, so
# it's kept weak. 0 would let a very wide table win on almost any word in a large warehouse.
BM25_K1 = 1.5
BM25_B = 0.3
# reciprocal rank fusion constant; 60 is the value from the original paper and the usual default
RRF_K = 60

WORD = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does", "each", "for", "from", "had", "has",
    "have", "how", "i", "in", "is", "it", "its", "many", "me", "much", "of", "on", "or", "our", "per", "show",
    "that", "the", "their", "there", "these", "this", "to", "was", "we", "were", "what", "when", "where", "which",
    "who", "whose", "with", "would", "you",
}


def tokenize(text: str) -> list[str]:
    # underscores split too, so seller_tier matches a question about "seller tier"
    words = WORD.findall(text.lower().replace("_", " "))
    return [_stem(word) for word in words if word not in STOP_WORDS]


def _stem(word: str) -> str:
    # just enough to match plurals: sellers -> seller, categories -> category
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def table_document(table: Table) -> str:
    parts = [table.name, table.grain, table.description]
    for column in table.columns:
        parts += [column.name, column.description, " ".join(str(v) for v in column.values)]
    return " ".join(part for part in parts if part)


def table_chunks(table: Table) -> list[str]:
    # one chunk for the table and one per column: a meaning match usually hits one column, not the whole table
    short_name = table.name.split(".")[-1]
    chunks = [f"{short_name}: {table.grain}. {table.description}"]
    for column in table.columns:
        values = f" Values: {', '.join(str(v) for v in column.values)}." if column.values else ""
        chunks.append(f"{short_name} {column.name.replace('_', ' ')}: {column.description}{values}")
    return chunks


class KeywordIndex:
    """BM25 over one document per table: names, descriptions, columns and listed values."""

    def __init__(self, tables: list[Table]):
        self.names = [t.name for t in tables]
        self.docs = [Counter(tokenize(table_document(t))) for t in tables]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        self.average_length = sum(self.lengths) / len(self.lengths)
        document_frequency = Counter(word for doc in self.docs for word in doc)
        total = len(self.docs)
        self.idf = {word: math.log(1 + (total - df + 0.5) / (df + 0.5)) for word, df in document_frequency.items()}

    def scores(self, question: str) -> dict[str, float]:
        words = tokenize(question)
        result = {}
        for name, doc, length in zip(self.names, self.docs, self.lengths):
            score = 0.0
            for word in words:
                count = doc.get(word, 0)
                if count:
                    norm = BM25_K1 * (1 - BM25_B + BM25_B * length / self.average_length)
                    score += self.idf[word] * count * (BM25_K1 + 1) / (count + norm)
            result[name] = score
        return result


class FastEmbedder:
    """Small local embedding model (ONNX, no PyTorch), downloaded once into index/models."""

    def __init__(self, model: str = DEFAULT_EMBEDDING_MODEL):
        # Windows can't create the shortcut links the model cache prefers without Developer Mode; copies work fine
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        try:
            from fastembed import TextEmbedding
        except ImportError as error:
            raise ConfigError("Embedding and hybrid retrieval need fastembed: python -m pip install -r requirements-retrieval.txt") from error
        self.model_name = model
        self.model = TextEmbedding(model, cache_dir=str(INDEX_DIR / "models"))

    def embed_passages(self, texts: list[str]):
        import numpy as np
        return np.array(list(self.model.passage_embed(texts)), dtype="float32")

    def embed_query(self, text: str):
        import numpy as np
        return np.array(list(self.model.query_embed([text]))[0], dtype="float32")


class EmbeddingIndex:
    """Cosine similarity between the question and every table and column chunk; a table scores as its best chunk."""

    def __init__(self, tables: list[Table], embedder, cache_dir: Path | None = INDEX_DIR):
        import numpy as np

        self.embedder = embedder
        self.owners, texts = [], []
        for table in tables:
            for chunk in table_chunks(table):
                self.owners.append(table.name)
                texts.append(chunk)
        self.vectors = _normalise(self._load_or_embed(texts, cache_dir))
        self.names = [t.name for t in tables]
        self._np = np

    def _load_or_embed(self, texts: list[str], cache_dir: Path | None):
        import numpy as np

        if cache_dir is None:
            return self.embedder.embed_passages(texts)
        # keyed by the model and the exact text, so any edit to the pack re-embeds it
        key = hashlib.sha256(("\n".join([getattr(self.embedder, "model_name", "")] + texts)).encode()).hexdigest()[:16]
        path = cache_dir / f"schema-{key}.npy"
        if path.exists():
            return np.load(path)
        vectors = self.embedder.embed_passages(texts)
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(path, vectors)
        return vectors

    def scores(self, question: str) -> dict[str, float]:
        query = _normalise(self.embedder.embed_query(question)[None, :])[0]
        similarity = self.vectors @ query
        result = {name: -1.0 for name in self.names}
        for owner, value in zip(self.owners, similarity):
            result[owner] = max(result[owner], float(value))
        return result


def _normalise(vectors):
    import numpy as np
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


def rank(scores: dict[str, float], order: list[str]) -> list[str]:
    # ties keep the pack's own order, so results are stable
    return sorted(order, key=lambda name: (-scores[name], order.index(name)))


def fuse(rankings: list[list[str]]) -> list[str]:
    """Reciprocal rank fusion: a table near the top of either ranking ends up near the top."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, name in enumerate(ranking, 1):
            fused[name] = fused.get(name, 0.0) + 1 / (RRF_K + position)
    order = rankings[0]
    return sorted(order, key=lambda name: (-fused[name], order.index(name)))


@dataclass
class SchemaRetriever:
    method: str
    top_k: int
    names: list[str]
    keyword: KeywordIndex | None = None
    embedding: EmbeddingIndex | None = None

    @classmethod
    def build(cls, pack: Pack, method: str, top_k: int, embedder=None, cache_dir: Path | None = INDEX_DIR,
              model: str = DEFAULT_EMBEDDING_MODEL) -> "SchemaRetriever":
        if method not in METHODS or method == "off":
            raise ConfigError(f"Schema retrieval method must be one of {', '.join(METHODS[1:])}, not '{method}'.")
        keyword = KeywordIndex(pack.tables) if method in ("keyword", "hybrid") else None
        embedding = None
        if method in ("embedding", "hybrid"):
            embedding = EmbeddingIndex(pack.tables, embedder or FastEmbedder(model), cache_dir)
        return cls(method, top_k, [t.name for t in pack.tables], keyword, embedding)

    def ranking(self, question: str) -> list[str]:
        rankings = []
        if self.keyword:
            rankings.append(rank(self.keyword.scores(question), self.names))
        if self.embedding:
            rankings.append(rank(self.embedding.scores(question), self.names))
        return rankings[0] if len(rankings) == 1 else fuse(rankings)

    def retrieve(self, question: str, top_k: int | None = None) -> list[str]:
        return self.ranking(question)[: top_k or self.top_k]


def reference_tables(sql: str, dialect: str) -> set[str]:
    """The tables a query reads, without CTE names: what retrieval must have included."""
    tree = sqlglot.parse_one(sql, read=dialect)
    ctes = {cte.alias.lower() for cte in tree.find_all(exp.CTE)}
    names = set()
    for table in tree.find_all(exp.Table):
        name = f"{table.db}.{table.name}".lower() if table.db else table.name.lower()
        if table.db or name not in ctes:
            names.add(name)
    return names


def schema_recall(retriever: SchemaRetriever, questions: list[tuple[str, str, set[str]]], top_k: int) -> tuple[int, list[tuple[str, list[str], list[str]]]]:
    """How many questions got every table their reference query reads, and which ones missed."""
    hits, misses = 0, []
    for question_id, question, needed in questions:
        got = [name.lower() for name in retriever.retrieve(question, top_k)]
        missing = sorted(needed - set(got))
        if missing:
            misses.append((question_id, missing, got))
        else:
            hits += 1
    return hits, misses

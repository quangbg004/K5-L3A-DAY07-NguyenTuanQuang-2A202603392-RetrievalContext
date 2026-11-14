"""Read the Day 6 index and expose dense, lexical and hybrid retrieval."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

from baseline import TfidfIndex
from convert_day6 import convert_chunk


class Day6Index:
    def __init__(self, lab: Path):
        sys.path.insert(0, str(lab.resolve() / "starter"))
        from dotenv import dotenv_values
        from src.embeddings import MyEmbedder
        from src.store import PgVectorStore
        import os

        self.env = {**dotenv_values(lab / "starter" / ".env"), **os.environ}
        model = "BAAI/bge-small-en-v1.5"
        start = perf_counter()
        self.embedder = MyEmbedder(model, str(lab / "starter" / ".venv" / "model-cache"))
        self.store = PgVectorStore(self.env["DATABASE_URL"], self.embedder.dimensions)
        with self.store.connect() as connection:
            rows = connection.execute("""
                SELECT chunk_id, document_id, source, page, text, metadata
                FROM day06_protocol_chunks
                WHERE strategy = 'B'
                ORDER BY chunk_id
            """).fetchall()
            fingerprint = connection.execute("""
                SELECT md5(string_agg(md5(embedding::text), '' ORDER BY chunk_id)) AS value
                FROM day06_protocol_chunks WHERE strategy = 'B'
            """).fetchone()["value"]
            versions = connection.execute("""
                SELECT current_setting('server_version') AS postgres, extversion AS pgvector
                FROM pg_extension WHERE extname = 'vector'
            """).fetchone()
        self.chunks = [convert_chunk(row) for row in rows]
        if not self.chunks:
            raise RuntimeError("Day 6 index B is empty. Run the Day 6 ingestion first.")
        self.lexical = TfidfIndex(self.chunks)
        self.info = {
            "strategy": "B", "embedding": model, "dimensions": self.embedder.dimensions,
            "database": versions, "chunks": len(self.chunks), "embedding_fingerprint": fingerprint,
            "corpus_sha256": sha256(json.dumps(self.chunks, sort_keys=True).encode()).hexdigest(),
            "setup_seconds": perf_counter() - start,
        }

    @lru_cache(maxsize=128)
    def query_vector(self, query):
        return self.embedder.embed_query(query)

    def search(self, method, query, top_k, filters=None):
        if method in ("dense", "hybrid"):
            pool = max(12, top_k) if method == "hybrid" else top_k
            dense = [{**convert_chunk(row), "score": row["score"]} for row in
                     self.store.search("B", self.query_vector(query), top_k=pool, filters=filters)]
            if method == "dense":
                return dense
        pool = max(12, top_k) if method == "hybrid" else top_k
        # Filter before cutting off the lexical ranking.
        lexical = [row for row in self.lexical.search(query, top_k=len(self.chunks))
                   if all(row["metadata"].get(k) == v for k, v in (filters or {}).items())][:pool]
        if method == "tfidf":
            return lexical
        return fuse(dense, lexical, top_k)


def fuse(dense, lexical, top_k):
    merged = {}
    for method, rows in (("dense", dense), ("tfidf", lexical)):
        for rank, row in enumerate(rows, 1):
            candidate = merged.setdefault(row["id"], {**row, "score": 0., "ranks": {}})
            candidate["ranks"][method] = rank
            candidate["score"] += 1 / (60 + rank)
    return sorted(merged.values(), key=lambda row: (-row["score"], row["id"]))[:top_k]


def question_filter(question):
    text = question.casefold()
    if "official" in text and "mcp" in text and "specification" in text:
        return {"document_type": "specification"}
    return None

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

from app.config import settings

logger = logging.getLogger(__name__)

_ef_cache: dict[str, Any] = {}


def _embedding_fn():
    key = settings.embedding_model
    if key not in _ef_cache:
        _ef_cache[key] = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=key,
        )
    return _ef_cache[key]


def _client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(settings.chroma_path))


def _chunks_collection():
    return _client().get_or_create_collection(
        name="document_chunks",
        embedding_function=_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


def _prefs_collection():
    return _client().get_or_create_collection(
        name="operator_preferences",
        embedding_function=_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


def index_chunks(document_id: str, chunks: list[tuple[str, str, int | None, str]]) -> None:
    """Index chunks: list of (chunk_id, text, page_index, source)."""
    col = _chunks_collection()
    if not chunks:
        return
    ids = [c[0] for c in chunks]
    documents = [c[1] for c in chunks]
    metadatas = [
        {
            "document_id": document_id,
            "page_index": -1 if c[2] is None else int(c[2]),
            "source": c[3],
        }
        for c in chunks
    ]
    col.delete(where={"document_id": document_id})
    col.add(ids=ids, documents=documents, metadatas=metadatas)


def delete_document_index(document_id: str) -> None:
    col = _chunks_collection()
    try:
        col.delete(where={"document_id": document_id})
    except Exception as e:  # noqa: BLE001
        logger.debug("Chroma delete: %s", e)


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def _tok(s: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(s)]


def reciprocal_rank_fusion(rank_lists: list[list[str]], k: int = 60) -> list[str]:
    scores: defaultdict[str, float] = defaultdict(float)
    for ranked in rank_lists:
        for r, doc_id in enumerate(ranked):
            scores[doc_id] += 1.0 / (k + r + 1)
    return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)


def hybrid_retrieve(
    document_id: str,
    query: str,
    chunk_rows: list[tuple[str, str, int | None]],
    top_n: int | None = None,
) -> tuple[list[tuple[str, str, int | None, float]], dict[str, Any]]:
    """
    chunk_rows: (chunk_id, text, page_index)
    Returns ranked list with fusion score in [0,1] approx, plus debug dict.
    """
    top_n = top_n or settings.retrieval_fusion_top_n
    debug: dict[str, Any] = {}

    id_to_row = {cid: (cid, text, page) for cid, text, page in chunk_rows}

    # Dense
    col = _chunks_collection()
    dense_ids: list[str] = []
    try:
        q = col.query(
            query_texts=[query],
            n_results=min(settings.retrieval_top_k_dense, max(1, len(chunk_rows))),
            where={"document_id": document_id},
        )
        dense_ids = list(q["ids"][0]) if q and q.get("ids") else []
    except Exception as e:  # noqa: BLE001
        logger.warning("Dense retrieval failed: %s", e)
        debug["dense_error"] = str(e)

    # BM25 in-memory over this document's chunks
    corpus = [_tok(t) for _, t, _ in chunk_rows]
    bm25_ids: list[str] = []
    if corpus and any(corpus):
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(_tok(query))
        order = sorted(range(len(chunk_rows)), key=lambda i: scores[i], reverse=True)
        bm25_ids = [chunk_rows[i][0] for i in order[: settings.retrieval_top_k_bm25]]

    fused = reciprocal_rank_fusion([dense_ids, bm25_ids])
    debug["dense_top"] = dense_ids[:10]
    debug["bm25_top"] = bm25_ids[:10]

    ranked: list[tuple[str, str, int | None, float]] = []
    for rank, cid in enumerate(fused):
        if cid not in id_to_row:
            continue
        cid, text, page = id_to_row[cid]
        score = 1.0 - (rank / max(1, len(fused)))
        ranked.append((cid, text, page, score))
        if len(ranked) >= top_n:
            break

    return ranked, debug


def retrieve_preferences(query: str, document_id: str | None, top_k: int = 5) -> list[str]:
    col = _prefs_collection()
    try:
        where: dict[str, Any] | None = None
        if document_id:
            where = {"document_id": document_id}
        res = col.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )
        docs = res.get("documents") or []
        if not docs or not docs[0]:
            return []
        return list(docs[0])
    except Exception:
        return []


def index_preference_snippet(document_id: str, snippet_id: str, text: str) -> None:
    col = _prefs_collection()
    col.upsert(
        ids=[snippet_id],
        documents=[text],
        metadatas=[{"document_id": document_id}],
    )

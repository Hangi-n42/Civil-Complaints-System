"""Hybrid 검색 (BM25 + Dense RRF 융합). (#274)

교정 평가(#273)에서 Hybrid이 전 지표 1위였다. 검증과의 충실성을 위해 **동일한
정규식 토크나이저·BM25 공식**(k1=1.5, b=0.75)을 쓰며, 프로덕션 지연을 위해 역색인으로
구현한다. Dense 결과(ChromaVectorStore.query 산출)와 Reciprocal Rank Fusion으로 융합.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[A-Za-z0-9가-힣]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _split_pipe_list(value: Any, *, uppercase: bool = False) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [item for item in value.split("|") if item]
    else:
        raw_items = []

    items: list[str] = []
    seen = set()
    for item in raw_items:
        text = " ".join(str(item or "").split())
        if uppercase:
            text = text.upper()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


class InvertedBM25:
    """역색인 기반 BM25 (build_fair_pool_qrels.py 검증 구현과 동일 공식)."""

    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.N = len(texts)
        self.doc_len: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = {}
        df: dict[str, int] = {}
        for i, text in enumerate(texts):
            toks = _tokenize(text)
            self.doc_len.append(len(toks))
            for term, tf in Counter(toks).items():
                self.postings.setdefault(term, []).append((i, tf))
                df[term] = df.get(term, 0) + 1
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        self.idf = {t: math.log(((self.N - n + 0.5) / (n + 0.5)) + 1) for t, n in df.items()}

    def top_k(self, query: str, k: int) -> list[int]:
        scores: dict[int, float] = {}
        for term in _tokenize(query):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in self.postings[term]:
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1))
                scores[i] = scores.get(i, 0.0) + idf * tf * (self.k1 + 1) / denom
        return sorted(scores, key=lambda i: scores[i], reverse=True)[:k]


class HybridRetriever:
    """BM25(역색인) + Dense를 RRF로 융합. collection별 BM25 인덱스는 lazy 빌드·캐시."""

    def __init__(self, store: Any, rrf_k: int = 60) -> None:
        self._store = store
        self.rrf_k = rrf_k
        self._coll: str | None = None
        self._bm25: InvertedBM25 | None = None
        self._case_ids: list[str] = []
        self._payload: dict[str, tuple[str, dict]] = {}

    def _ensure_index(self, collection_name: str) -> None:
        if self._bm25 is not None and self._coll == collection_name:
            return
        col = self._store._get_collection(collection_name)
        got = col.get(include=["documents", "metadatas"])
        ids, docs, metas = got.get("ids", []), got.get("documents", []), got.get("metadatas", [])
        case_ids, texts, payload, seen = [], [], {}, set()
        for storage_id, doc, meta in zip(ids, docs, metas):
            meta = meta or {}
            case_id = str(meta.get("case_id") or storage_id)
            if case_id in seen:
                continue
            seen.add(case_id)
            case_ids.append(case_id)
            texts.append(str(doc or ""))
            payload[case_id] = (str(doc or ""), meta)
        self._bm25 = InvertedBM25(texts)
        self._case_ids = case_ids
        self._payload = payload
        self._coll = collection_name
        logger.info(f"[Hybrid] BM25 인덱스 빌드: {collection_name} ({len(case_ids)} case)")

    def _result_dict(self, case_id: str, score: float, rank: int) -> dict[str, Any]:
        doc, meta = self._payload[case_id]
        obs = str(meta.get("summary_observation") or "")
        req = str(meta.get("summary_request") or "")
        return {
            "doc_id": str(meta.get("doc_id") or case_id),
            "case_id": case_id,
            "score": round(score, 6),
            "chunk_id": str(meta.get("chunk_id") or ""),
            "title": str(meta.get("title") or obs),
            "snippet": " ".join(doc.split())[:600],
            "summary": {"observation": obs, "request": req},
            "metadata": {
                "category": str(meta.get("category") or ""),
                "region": str(meta.get("region") or ""),
                "created_at": str(meta.get("created_at") or ""),
                "entity_labels": _split_pipe_list(meta.get("entity_labels"), uppercase=True),
                "entity_texts": _split_pipe_list(meta.get("entity_texts")),
                "legal_ref_names": _split_pipe_list(meta.get("legal_ref_names")),
                "legal_ref_ids": _split_pipe_list(meta.get("legal_ref_ids")),
                "key_terms": _split_pipe_list(meta.get("key_terms")),
                "responsible_units": _split_pipe_list(meta.get("responsible_units")),
                "responsible_units_source": str(meta.get("responsible_units_source") or ""),
                "responsible_units_confidence": float(meta.get("responsible_units_confidence") or 0.0),
                "urgency_level": str(meta.get("urgency_level") or ""),
            },
            "rank": rank,
            "retrieval": "hybrid",
        }

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int,
        dense_results: list[dict[str, Any]],
        fanout: int = 50,
    ) -> list[dict[str, Any]]:
        self._ensure_index(collection_name)
        assert self._bm25 is not None

        bm25_idx = self._bm25.top_k(query, fanout)
        bm25_rank = {self._case_ids[i]: r for r, i in enumerate(bm25_idx, 1)}

        dense_rank: dict[str, int] = {}
        for r, item in enumerate(dense_results, 1):
            cid = str(item.get("case_id") or item.get("doc_id") or "")
            if cid and cid not in dense_rank:
                dense_rank[cid] = r

        fused: dict[str, float] = {}
        for cid in set(bm25_rank) | set(dense_rank):
            s = 0.0
            if cid in bm25_rank:
                s += 1.0 / (self.rrf_k + bm25_rank[cid])
            if cid in dense_rank:
                s += 1.0 / (self.rrf_k + dense_rank[cid])
            fused[cid] = s

        ordered = sorted(fused, key=lambda c: fused[c], reverse=True)[:top_k]
        return [
            self._result_dict(cid, fused[cid], rank)
            for rank, cid in enumerate(ordered, 1)
            if cid in self._payload
        ]

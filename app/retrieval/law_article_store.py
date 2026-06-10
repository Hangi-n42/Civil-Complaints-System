"""조문 코퍼스 인덱싱 + 검색 (Hybrid) — Phase B.

law_articles.json(조 단위 레코드)을 bge-m3 로 임베딩해 Chroma 컬렉션
`law_articles_v1` 에 적재하고, **Phase A 의 legal_refs.law_id 로 법령을 필터**한 뒤
**Dense(bge-m3) + Sparse(BM25)** 를 RRF 로 융합해 조문을 검색한다.

  민원 ─▶ BE1.legal_refs(law_id) ─▶ law_id 필터
       ─▶ Dense(의미) ⊕ BM25(정확 용어) ─RRF─▶ Top 조문 ─▶ BE3 컨텍스트

설계:
  - 법조문은 "이행강제금/가설건축물" 같은 정확 용어가 결정적 → BM25 병행이 중요.
  - 무거운 의존성(chromadb/sentence_transformers)은 지연 임포트하고, 미설치/모델 부재 시
    **BM25 단독으로 자동 폴백**(이 환경에서 실제 코퍼스로 검증 가능).
  - 순수 로직(tokenize/BM25Index/rrf_fuse/rank_articles)은 모델 없이 테스트 가능.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

COLLECTION_NAME = "law_articles_v1"
CORPUS_FILENAME = "law_articles.json"

_KEYTERM_BOOST = 0.03
_MAX_BOOST_TERMS = 5
_RRF_K = 60

_TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z0-9]+")


_HANGUL_RE = re.compile(r"^[가-힣]+$")


def _normalize_chroma_client_path(persist_directory: str | Path) -> str:
    """Windows 한글 절대 경로를 Chroma가 읽을 수 있는 상대 경로로 바꾼다."""

    path = Path(persist_directory)
    try:
        return os.path.relpath(str(path.resolve()), start=str(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


def tokenize(text: str) -> List[str]:
    """한글/영숫자 어절 + 한글 문자 bigram 토큰화.

    법조문은 '건설기계조종사면허'·'정기적성검사'처럼 복합어가 붙어 있어,
    어절만으로는 질의 '면허'·'적성검사' 와 안 맞는다. 한글 어절은 2-gram 으로도
    쪼개 부분 매칭(BM25 recall)을 살린다.
    """
    out: List[str] = []
    for w in _TOKEN_RE.findall(text or ""):
        if len(w) < 2:
            continue
        out.append(w)
        if _HANGUL_RE.match(w):
            out.extend(w[i:i + 2] for i in range(len(w) - 1))
    return out


# ──────────────────────────────────────────────────────────────────────────
# BM25 (순수)
# ──────────────────────────────────────────────────────────────────────────
class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: List[str] = []
        self.tf: List[Counter] = []
        self.doclen: List[int] = []
        self.idf: Dict[str, float] = {}
        self.avgdl: float = 0.0

    def fit(self, doc_ids: List[str], token_lists: List[List[str]]) -> "BM25Index":
        self.doc_ids = doc_ids
        self.tf = [Counter(t) for t in token_lists]
        self.doclen = [len(t) for t in token_lists]
        n = len(token_lists)
        self.avgdl = (sum(self.doclen) / n) if n else 0.0
        df: Dict[str, int] = {}
        for toks in token_lists:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        return self

    def scores(self, query_tokens: List[str], candidate_idx: Optional[List[int]] = None) -> Dict[str, float]:
        qset = [t for t in query_tokens if t in self.idf]
        if not qset:
            return {}
        idxs = candidate_idx if candidate_idx is not None else range(len(self.doc_ids))
        out: Dict[str, float] = {}
        for i in idxs:
            tf = self.tf[i]
            dl = self.doclen[i]
            s = 0.0
            for t in qset:
                f = tf.get(t, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                s += self.idf[t] * (f * (self.k1 + 1)) / denom
            if s > 0:
                out[self.doc_ids[i]] = s
        return out


def rrf_fuse(rankings: List[List[str]], k: int = _RRF_K) -> List[Tuple[str, float]]:
    """여러 순위 리스트를 Reciprocal Rank Fusion 으로 융합."""
    scores: Dict[str, float] = {}
    for ids in rankings:
        for rank, doc_id in enumerate(ids):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def rank_articles(
    hits: List[Dict[str, Any]],
    key_terms: Optional[List[str]] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Dense 히트를 핵심어 부스트로 재정렬(Dense 측 랭킹)."""
    key_terms = [t for t in (key_terms or []) if t]
    ranked: List[Dict[str, Any]] = []
    for h in hits:
        sim = max(0.0, min(1.0, float(h.get("similarity", 0.0))))
        text = str(h.get("text", ""))
        n = sum(1 for t in key_terms if t in text)
        score = round(min(1.0, sim + _KEYTERM_BOOST * min(n, _MAX_BOOST_TERMS)), 4)
        item = dict(h)
        item["score"] = score
        item.pop("similarity", None)
        ranked.append(item)
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:top_k]


class LawArticleStore:
    """조문 코퍼스 인덱싱/검색기 (Dense bge-m3 + Sparse BM25, law_id 필터)."""

    def __init__(
        self,
        corpus_path: Optional[str] = None,
        persist_directory: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
        embedding_device: Optional[str] = None,
    ) -> None:
        from app.core.config import PROJECT_ROOT, settings

        self.corpus_path = Path(corpus_path) if corpus_path else (PROJECT_ROOT / "data" / "laws" / CORPUS_FILENAME)
        self.persist_directory = persist_directory or settings.CHROMA_DB_PATH
        self.embedding_model_name = embedding_model_name or settings.EMBEDDING_MODEL
        self.embedding_device = embedding_device or settings.EMBEDDING_DEVICE
        self._model = None
        self._client = None
        self._collection = None
        # BM25/코퍼스 캐시
        self._records: Optional[List[Dict[str, Any]]] = None
        self._docid_to_idx: Dict[str, int] = {}
        self._lawid_to_idx: Dict[str, List[int]] = {}
        self._bm25: Optional[BM25Index] = None

    # ── 임베딩 / 컬렉션 (지연 로딩) ───────────────────────────────────────
    def _get_model(self):
        if self._model is None:
            device = str(self.embedding_device or "cpu").strip().lower()
            if device == "cuda":
                try:
                    import torch
                    if not torch.cuda.is_available():
                        device = "cpu"
                except Exception:
                    device = "cpu"
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.embedding_model_name, device=device)
        return self._model

    def _embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self._get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vecs.tolist() if hasattr(vecs, "tolist") else [list(v) for v in vecs]

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=_normalize_chroma_client_path(self.persist_directory)
            )
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── 코퍼스 / BM25 (지연 로딩) ────────────────────────────────────────
    def _corpus(self) -> List[Dict[str, Any]]:
        if self._records is None:
            data = json.loads(self.corpus_path.read_text(encoding="utf-8"))
            self._records = data if isinstance(data, list) else []
            # doc_id 유니크화: 동일 법령 내 같은 조번호가 둘 이상이면 '#n' 접미(원문 조번호 중복 대응).
            seen: Dict[str, int] = {}
            for r in self._records:
                did = r.get("doc_id", "")
                if did in seen:
                    seen[did] += 1
                    r["doc_id"] = f"{did}#{seen[did]}"
                else:
                    seen[did] = 1
            for i, r in enumerate(self._records):
                self._docid_to_idx[r["doc_id"]] = i
                self._lawid_to_idx.setdefault(str(r.get("law_id", "")), []).append(i)
        return self._records

    def _get_bm25(self) -> BM25Index:
        if self._bm25 is None:
            recs = self._corpus()
            self._bm25 = BM25Index().fit(
                [r["doc_id"] for r in recs],
                [tokenize(r.get("text", "")) for r in recs],
            )
        return self._bm25

    # ── 인덱스 빌드 (Dense) ──────────────────────────────────────────────
    def build_index(self, rebuild: bool = False, batch_size: int = 128) -> Dict[str, int]:
        """Dense 인덱싱 (체크포인트/재개 지원).

        - rebuild=True : 컬렉션 삭제 후 처음부터.
        - rebuild=False: 컬렉션에 '이미 있는 doc_id' 는 건너뛰고 **끊긴 지점부터 이어서** 색인.
        ChromaDB(PersistentClient)는 배치 upsert 마다 디스크에 영속화하므로, 중단 시
        손실은 진행 중이던 배치(최대 batch_size)뿐이다. 끊겨도 다시 실행하면 이어서 진행된다.
        """
        collection = self._get_collection()
        if rebuild:
            self._client.delete_collection(COLLECTION_NAME)
            self._collection = None
            collection = self._get_collection()

        records = self._corpus()
        existing: set = set()
        if not rebuild:
            try:
                existing = set(collection.get(include=[]).get("ids", []))
            except Exception:
                existing = set()

        todo = [r for r in records if r["doc_id"] not in existing]
        total = len(todo)
        if total == 0:
            return {"articles": collection.count(), "indexed": 0, "skipped": len(records)}

        indexed = 0
        for i in range(0, total, batch_size):
            chunk = todo[i:i + batch_size]
            collection.upsert(
                ids=[r["doc_id"] for r in chunk],
                documents=[r["text"] for r in chunk],
                embeddings=self._embed([r["text"] for r in chunk]),
                metadatas=[{
                    "law_id": r.get("law_id", ""),
                    "law_name": r.get("law_name", ""),
                    "article_no": r.get("article_no", ""),
                    "doc_type": r.get("doc_type", ""),
                    "enforce_date": r.get("enforce_date", ""),
                    "source_url": r.get("source_url", ""),
                } for r in chunk],
            )
            indexed += len(chunk)
            print(f"  [law_articles] {indexed}/{total} 색인 "
                  f"(누적 {len(existing) + indexed}/{len(records)})", flush=True)
        return {"articles": collection.count(), "indexed": indexed,
                "skipped": len(records) - indexed}

    # ── 검색 (Hybrid: Dense ⊕ BM25, RRF) ─────────────────────────────────
    def _dense_ids(self, query_text: str, law_ids: Optional[List[str]], fetch_k: int,
                   key_terms: Optional[List[str]]) -> List[Dict[str, Any]]:
        """Dense 히트(키워드 부스트 적용). 모델/Chroma 미가용 시 []."""
        try:
            collection = self._get_collection()
            q_vec = self._embed([query_text])[0]
            where = {"law_id": {"$in": [str(x) for x in law_ids if x]}} if law_ids else None
            res = collection.query(query_embeddings=[q_vec], n_results=fetch_k,
                                   where=where, include=["metadatas", "distances", "documents"])
            ids = (res.get("ids") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            docs = (res.get("documents") or [[]])[0]
            hits = [{"doc_id": did, "law_name": m.get("law_name", ""), "law_id": m.get("law_id", ""),
                     "article_no": m.get("article_no", ""), "doc_type": m.get("doc_type", ""),
                     "source_url": m.get("source_url", ""), "text": doc, "similarity": 1.0 - float(dist)}
                    for did, m, dist, doc in zip(ids, metas, dists, docs)]
            return rank_articles(hits, key_terms=key_terms, top_k=fetch_k)
        except Exception:
            return []

    def _bm25_ranked(self, query_text: str, key_terms: Optional[List[str]],
                     law_ids: Optional[List[str]], fetch_k: int) -> List[str]:
        """BM25 doc_id 순위. 코퍼스 미존재 시 []."""
        try:
            bm25 = self._get_bm25()
        except Exception:
            return []
        q_tokens = tokenize(query_text) + [t for t in (key_terms or []) for t in tokenize(t)]
        cand = None
        if law_ids:
            cand = []
            for lid in law_ids:
                cand.extend(self._lawid_to_idx.get(str(lid), []))
            cand = sorted(set(cand))
        scored = bm25.scores(q_tokens, candidate_idx=cand)
        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:fetch_k]
        return [doc_id for doc_id, _ in ranked]

    def search(
        self,
        query_text: str,
        law_ids: Optional[List[str]] = None,
        key_terms: Optional[List[str]] = None,
        top_k: int = 5,
        fetch_k: int = 30,
    ) -> List[Dict[str, Any]]:
        """Hybrid 조문 검색. law_ids 로 법령 한정(Phase A 연결). Dense 불가 시 BM25 단독."""
        dense = self._dense_ids(query_text, law_ids, fetch_k, key_terms)
        sparse_ids = self._bm25_ranked(query_text, key_terms, law_ids, fetch_k)

        fused = rrf_fuse([[d["doc_id"] for d in dense if d.get("doc_id")], sparse_ids])
        if not fused:  # 둘 다 비면 dense 순서라도
            fused = [(d["doc_id"], d.get("score", 0.0)) for d in dense]

        recmap: Dict[str, Dict[str, Any]] = {d["doc_id"]: d for d in dense if d.get("doc_id")}
        corpus_map = None
        out: List[Dict[str, Any]] = []
        for doc_id, fscore in fused[:top_k]:
            rec = recmap.get(doc_id)
            if rec is None:
                if corpus_map is None:
                    self._corpus()
                    corpus_map = self._docid_to_idx
                idx = corpus_map.get(doc_id)
                if idx is None:
                    continue
                rec = dict(self._records[idx])
            else:
                rec = dict(rec)
            rec["score"] = round(float(fscore), 6)
            rec.pop("similarity", None)
            out.append(rec)
        return out


_store: Optional[LawArticleStore] = None


def get_law_article_store() -> LawArticleStore:
    global _store
    if _store is None:
        _store = LawArticleStore()
    return _store

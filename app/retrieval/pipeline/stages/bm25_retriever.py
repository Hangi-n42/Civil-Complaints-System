"""bm25s 기반 BM25 희소 검색 단계."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput


_DEFAULT_INDEX_DIR = "data/bm25_index"
_DEFAULT_COLLECTION = "civil_cases_v1"


class BM25RetrieveStage:
    """ChromaDB 전체 문서로 bm25s 인덱스를 빌드/로드하고 BM25 검색을 수행한다."""

    def __init__(
        self,
        *,
        name: str = "bm25_retriever",
        collection: str = _DEFAULT_COLLECTION,
        top_k: int = 50,
        index_dir: str = _DEFAULT_INDEX_DIR,
    ) -> None:
        self.name = name
        self.collection = collection
        self.top_k = top_k
        self.index_dir = Path(index_dir)
        self._retriever = None   # bm25s.BM25 — lazy load
        self._doc_ids: list[str] = []

    def _get_retriever(self):
        if self._retriever is not None:
            return self._retriever

        import bm25s

        index_path = self.index_dir / self.collection
        if index_path.exists():
            self._retriever = bm25s.BM25.load(str(index_path), load_corpus=True)
            corpus = self._retriever.corpus
            self._doc_ids = [doc["id"] for doc in corpus]
        else:
            doc_ids, texts = _load_corpus_from_chroma(self.collection)
            tokenized = bm25s.tokenize(texts, stopwords=None)
            retriever = bm25s.BM25()
            retriever.index(tokenized)
            corpus = [{"id": did, "text": text} for did, text in zip(doc_ids, texts)]
            retriever.corpus = corpus
            index_path.mkdir(parents=True, exist_ok=True)
            retriever.save(str(index_path), corpus=corpus)
            self._retriever = retriever
            self._doc_ids = doc_ids

        return self._retriever

    async def run(self, stage_input: StageInput) -> StageOutput:
        import bm25s

        query_text = stage_input.query.text
        retriever = self._get_retriever()
        corpus = retriever.corpus

        started_at = time.perf_counter()
        tokenized_query = bm25s.tokenize([query_text], stopwords=None)
        results, scores = retriever.retrieve(tokenized_query, k=min(self.top_k, len(corpus)))
        latency_ms = (time.perf_counter() - started_at) * 1000

        docs = [
            RetrievedDoc(
                qid=stage_input.query.qid,
                docid=str(results[0, rank]["id"]),
                score=float(scores[0, rank]),
                rank=rank + 1,
                stage=self.name,
                metadata={"snippet": str(results[0, rank].get("text") or "")[:200]},
            )
            for rank in range(results.shape[1])
        ]

        return StageOutput(
            stage_name=self.name,
            query=stage_input.query,
            candidates=docs,
            latency_ms=latency_ms,
        )


def _load_corpus_from_chroma(collection_name: str) -> tuple[list[str], list[str]]:
    """ChromaDB에서 전체 문서(chunk_text)와 case_id를 읽어온다."""
    import chromadb
    from app.core.config import settings

    client = chromadb.PersistentClient(path=str(settings.CHROMA_DB_PATH))
    collection = client.get_collection(collection_name)
    total = collection.count()

    batch_size = 1000
    doc_ids: list[str] = []
    texts: list[str] = []

    for offset in range(0, total, batch_size):
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["documents", "metadatas"],
        )
        for doc, meta in zip(batch["documents"], batch["metadatas"]):
            case_id = str((meta or {}).get("case_id") or "")
            doc_ids.append(case_id)
            texts.append(str(doc or ""))

    return doc_ids, texts

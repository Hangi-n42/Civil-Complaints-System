"""bm25s 기반 BM25 희소 검색 단계."""

from __future__ import annotations

import time
from pathlib import Path

from app.core.config import settings
from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput


_DEFAULT_INDEX_DIR = "data/bm25_index"
_DEFAULT_COLLECTION = settings.DEFAULT_CHROMA_COLLECTION

# kiwipiepy에서 의미 있는 품사만 추출 (명사, 용언 어근, 외래어, 한자)
_KIWI_KEEP_TAGS = {"NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "XR", "SL", "SH"}


def _tokenize_korean(texts: list[str]) -> list[list[str]]:
    """kiwipiepy로 형태소 분석 후 의미 있는 어절만 반환."""
    from kiwipiepy import Kiwi

    kiwi = Kiwi()
    result = []
    for text in kiwi.tokenize(texts, normalize_coda=True):
        morphs = [t.form for t in text if t.tag in _KIWI_KEEP_TAGS and len(t.form) > 1]
        result.append(morphs if morphs else text.split() if isinstance(text, str) else [])
    return result


def _tokenize_whitespace(texts: list[str]) -> list[list[str]]:
    """공백 기준 단순 분리."""
    return [text.split() for text in texts]


class BM25RetrieveStage:
    """ChromaDB 전체 문서로 bm25s 인덱스를 빌드/로드하고 BM25 검색을 수행한다.

    tokenizer 파라미터:
        'whitespace' (기본): 공백 분리 — 빠르지만 한국어 조사·어미 미처리
        'korean': kiwipiepy 형태소 분석 — 어근 단위 인덱싱으로 재현율 향상
    """

    def __init__(
        self,
        *,
        name: str = "bm25_retriever",
        collection: str = _DEFAULT_COLLECTION,
        top_k: int = 50,
        index_dir: str = _DEFAULT_INDEX_DIR,
        tokenizer: str = "whitespace",
    ) -> None:
        self.name = name
        self.collection = collection
        self.top_k = top_k
        self.index_dir = Path(index_dir)
        self.tokenizer = tokenizer
        self._retriever = None
        self._doc_ids: list[str] = []

    def _index_path(self) -> Path:
        """tokenizer 종류별로 다른 경로에 저장하여 충돌을 방지한다."""
        return self.index_dir / f"{self.collection}_{self.tokenizer}"

    def _tokenize(self, texts: list[str]) -> list[list[str]]:
        if self.tokenizer == "korean":
            return _tokenize_korean(texts)
        return _tokenize_whitespace(texts)

    def _get_retriever(self):
        if self._retriever is not None:
            return self._retriever

        import bm25s

        index_path = self._index_path()
        if index_path.exists():
            self._retriever = bm25s.BM25.load(str(index_path), load_corpus=True)
            self._doc_ids = [doc["id"] for doc in self._retriever.corpus]
        else:
            doc_ids, texts = _load_corpus_from_chroma(self.collection)
            tokenized_corpus = self._tokenize(texts)
            retriever = bm25s.BM25()
            retriever.index(bm25s.tokenize(texts, stopwords=None) if self.tokenizer == "whitespace"
                            else _to_bm25s_tokens(tokenized_corpus))
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

        if self.tokenizer == "korean":
            query_tokens = self._tokenize([query_text])[0]
            tokenized_query = _to_bm25s_tokens([query_tokens])
        else:
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


def _to_bm25s_tokens(tokenized: list[list[str]]):
    """형태소 분석 결과를 bm25s가 받을 수 있는 형태로 변환한다."""
    import bm25s

    # bm25s.tokenize는 문자열 리스트를 받으므로, 이미 분리된 토큰은 공백으로 합쳐서 넘긴다
    joined = [" ".join(tokens) for tokens in tokenized]
    return bm25s.tokenize(joined, stopwords=None)


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

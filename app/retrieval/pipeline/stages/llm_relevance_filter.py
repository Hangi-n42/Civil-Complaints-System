"""LLM 관련성 필터 단계 (#301, 코어는 #305에서 app.retrieval.grounding_filter로 단일화).

상위 후보를 LLM(관련성 루브릭)으로 0/1/2 채점하고, 임계값 미만(기본 rel0)을 제거한 뒤
점수 desc로 재정렬해 top_k를 남긴다. RAG grounding에서 해로운(rel0) 선례를 근거에서 배제.

근거(#299): Hybrid top-5의 23%가 rel0(주입 시 할루시네이션 유발). LLM 리랭커를 '재정렬'로
쓰면 미미(23→20%)했지만 '필터(0점 제거)'로 쓰니 해로움 23%→4%.

필터/채점 로직은 app.retrieval.grounding_filter(프로덕션 search()와 공유)에 있다.
이 모듈은 그 코어를 파이프라인 스테이지 계약(StageInput/StageOutput)에 어댑트한다.
"""

from __future__ import annotations

import time

from app.core.config import settings
from app.retrieval.grounding_filter import (
    extract_score as _extract_score,  # 하위호환 재노출
    filter_by_relevance,
    score_relevance,
)
from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput
from app.retrieval.pipeline.stages.cross_encoder_rerank import _get_text

__all__ = ["LLMRelevanceFilterStage", "_extract_score"]


class LLMRelevanceFilterStage:
    """상위 후보를 LLM 관련성으로 채점 → 임계값 미만 제거 → 재정렬."""

    def __init__(
        self,
        *,
        name: str = "llm_relevance_filter",
        model: str | None = None,
        top_k: int = 5,
        min_score: int = 1,
        rerank_pool: int = 10,
        max_chars: int = 600,
        max_concurrency: int = 4,
    ) -> None:
        self.name = name
        self.model = model or settings.OLLAMA_MODEL
        self.top_k = top_k
        self.min_score = min_score
        self.rerank_pool = rerank_pool
        self.max_chars = max_chars
        self.max_concurrency = max_concurrency
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._timeout = settings.OLLAMA_TIMEOUT

    async def _score(self, query_text: str, doc_text: str) -> int | None:
        """후보 1건 채점(공유 코어 위임). 테스트는 이 메서드를 mock한다."""
        return await score_relevance(
            query_text, doc_text,
            model=self.model, base_url=self._base_url, timeout=self._timeout, max_chars=self.max_chars,
        )

    async def run(self, stage_input: StageInput) -> StageOutput:
        candidates = list(stage_input.candidates)
        if not candidates:
            return StageOutput(stage_name=self.name, query=stage_input.query, candidates=[], latency_ms=0.0)

        started_at = time.perf_counter()
        kept = await filter_by_relevance(
            stage_input.query.text, candidates,
            get_text=_get_text, score_fn=self._score,
            min_score=self.min_score, rerank_pool=self.rerank_pool,
            top_k=self.top_k, max_concurrency=self.max_concurrency,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000

        filtered = [
            RetrievedDoc(qid=doc.qid, docid=doc.docid, score=score, rank=rank, stage=self.name, metadata=doc.metadata)
            for rank, (doc, score) in enumerate(kept, start=1)
        ]
        return StageOutput(
            stage_name=self.name,
            query=stage_input.query,
            candidates=filtered,
            latency_ms=latency_ms,
            metadata={"scored": min(len(candidates), self.rerank_pool), "kept": len(filtered)},
        )

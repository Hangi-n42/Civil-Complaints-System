"""기준선 평가 파이프라인에서 사용하는 Chroma dense 검색 단계."""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput
from app.retrieval.router.adaptive_router import route
from app.retrieval.service import RetrievalService, get_retrieval_service


class ChromaDenseStage:
    def __init__(
        self,
        *,
        name: str = "dense_retriever",
        collection: str = settings.DEFAULT_CHROMA_COLLECTION,
        top_k: int = 10,
        use_adaptive_router: bool = False,
        snippet_max_chars: int = 140,
        service: RetrievalService | None = None,
    ) -> None:
        self.name = name
        self.collection = collection
        self.top_k = top_k
        self.use_adaptive_router = use_adaptive_router
        self.snippet_max_chars = snippet_max_chars
        self.service = service or get_retrieval_service()

    async def run(self, stage_input: StageInput) -> StageOutput:
        query = stage_input.query
        metadata = query.metadata
        top_k = self.top_k
        retrieval_policy = metadata.get("retrieval_policy")
        snippet_max_chars = metadata.get("snippet_max_chars") or self.snippet_max_chars

        if self.use_adaptive_router:
            decision = route(
                topic_type=str(metadata.get("topic_type") or "general"),
                complexity_level=str(metadata.get("complexity_level") or "medium"),
                complexity_score=float(metadata.get("complexity_score") or 0.5),
            )
            top_k = decision.applied_params.top_k
            retrieval_policy = decision.retrieval_policy
            snippet_max_chars = decision.applied_params.snippet_max_chars

        started_at = time.perf_counter()
        raw_results = await self.service.search(
            query=query.text,
            top_k=top_k,
            collection_name=self.collection,
            topic_type=str(metadata.get("topic_type") or "general"),
            retrieval_policy=str(retrieval_policy or "general"),
            snippet_max_chars=int(snippet_max_chars or 140),
            strategy="dense",  # dense 전용 단계 — 전역 hybrid 기본값에 영향받지 않도록 고정
        )
        latency_ms = (time.perf_counter() - started_at) * 1000

        docs = [
            RetrievedDoc(
                qid=query.qid,
                docid=_result_docid(item),
                score=float(item.get("score") or 0.0),
                rank=int(item.get("rank") or index),
                stage=self.name,
                metadata=_result_metadata(item),
            )
            for index, item in enumerate(raw_results, start=1)
        ]
        return StageOutput(stage_name=self.name, query=query, candidates=docs, latency_ms=latency_ms)


def _result_docid(item: dict[str, Any]) -> str:
    return str(item.get("case_id") or item.get("doc_id") or item.get("chunk_id") or "")


def _result_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(item.get("metadata") or {})
    for key in ("case_id", "doc_id", "chunk_id", "title", "category", "region", "snippet", "summary"):
        if key in item:
            metadata[key] = item[key]
    return metadata

"""Cross-encoder 기반 reranker 단계."""

from __future__ import annotations

import time
from typing import Any

from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput


class CrossEncoderRerankStage:
    """상위 K 후보를 cross-encoder로 재점수화한다."""

    def __init__(
        self,
        *,
        name: str = "cross_encoder_rerank",
        model_name: str = "BAAI/bge-reranker-v2-m3",
        top_k: int = 10,
        batch_size: int = 32,
    ) -> None:
        self.name = name
        self.top_k = top_k
        self.batch_size = batch_size
        self._model_name = model_name
        self._model = None  # 첫 호출 시 lazy load

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model

    async def run(self, stage_input: StageInput) -> StageOutput:
        candidates = list(stage_input.candidates)
        if not candidates:
            return StageOutput(stage_name=self.name, query=stage_input.query, candidates=[], latency_ms=0.0)

        query_text = stage_input.query.text
        pairs = [[query_text, _get_text(doc)] for doc in candidates]

        started_at = time.perf_counter()
        model = self._get_model()
        scores: list[float] = model.predict(pairs, batch_size=self.batch_size).tolist()
        latency_ms = (time.perf_counter() - started_at) * 1000

        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        reranked_docs = [
            RetrievedDoc(
                qid=doc.qid,
                docid=doc.docid,
                score=score,
                rank=rank,
                stage=self.name,
                metadata=doc.metadata,
            )
            for rank, (doc, score) in enumerate(ranked[: self.top_k], start=1)
        ]

        return StageOutput(
            stage_name=self.name,
            query=stage_input.query,
            candidates=reranked_docs,
            latency_ms=latency_ms,
        )


def _get_text(doc: RetrievedDoc) -> str:
    meta = doc.metadata
    title = str(meta.get("title") or "")

    summary = meta.get("summary") or {}
    if isinstance(summary, dict):
        observation = str(summary.get("observation") or "")
        request = str(summary.get("request") or "")
        body = " ".join(part for part in (observation, request) if part)
    else:
        body = ""

    if not body:
        body = str(meta.get("snippet") or "")

    if title and body:
        return f"{title} {body}"
    return title or body or doc.docid

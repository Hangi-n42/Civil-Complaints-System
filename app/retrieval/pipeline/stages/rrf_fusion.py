"""Reciprocal Rank Fusion(RRF) 병합 단계."""

from __future__ import annotations

import time

from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput


class RRFFusionStage:
    """지정한 이전 stage들의 후보를 RRF로 통합한다.

    RRF 점수 공식: score(d) = Σ 1 / (k + rank_i(d))
    참고: Cormack et al. (2009)
    """

    def __init__(
        self,
        *,
        name: str = "rrf_fusion",
        source_stages: list[str] | None = None,
        top_k: int = 10,
        k: int = 60,
    ) -> None:
        self.name = name
        self.source_stages = source_stages  # None이면 직전 stage만 사용 (단독 실행 불가)
        self.top_k = top_k
        self.k = k

    async def run(self, stage_input: StageInput) -> StageOutput:
        started_at = time.perf_counter()

        # runner가 context에 이전 stage 출력을 담아 전달
        all_outputs: dict = stage_input.context.get("stage_outputs") or {}

        if self.source_stages:
            sources = {
                name: out.candidates
                for name, out in all_outputs.items()
                if name in self.source_stages
            }
        else:
            # source_stages 미지정 시 context의 모든 stage 사용
            sources = {name: out.candidates for name, out in all_outputs.items()}

        if not sources:
            # fallback: 직전 stage 후보를 그대로 반환
            return StageOutput(
                stage_name=self.name,
                query=stage_input.query,
                candidates=list(stage_input.candidates)[: self.top_k],
                latency_ms=0.0,
            )

        rrf_scores: dict[str, float] = {}
        doc_ref: dict[str, RetrievedDoc] = {}

        for candidates in sources.values():
            for doc in candidates:
                rank = doc.rank if doc.rank > 0 else 1
                rrf_scores[doc.docid] = rrf_scores.get(doc.docid, 0.0) + 1.0 / (self.k + rank)
                # metadata가 더 풍부한 doc을 대표로 저장 (같으면 점수 높은 것 우선)
                prev = doc_ref.get(doc.docid)
                if prev is None or len(doc.metadata) > len(prev.metadata):
                    doc_ref[doc.docid] = doc
                elif len(doc.metadata) == len(prev.metadata) and doc.score > prev.score:
                    doc_ref[doc.docid] = doc

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        latency_ms = (time.perf_counter() - started_at) * 1000

        fused_docs = [
            RetrievedDoc(
                qid=stage_input.query.qid,
                docid=docid,
                score=score,
                rank=rank,
                stage=self.name,
                metadata=doc_ref[docid].metadata,
            )
            for rank, (docid, score) in enumerate(ranked[: self.top_k], start=1)
        ]

        return StageOutput(
            stage_name=self.name,
            query=stage_input.query,
            candidates=fused_docs,
            latency_ms=latency_ms,
        )

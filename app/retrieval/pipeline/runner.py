"""선언적 검색 파이프라인 실행기."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.evaluation.datasets import EvalQuery
from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput
from app.retrieval.pipeline.stages.bm25_retriever import BM25RetrieveStage
from app.retrieval.pipeline.stages.chroma_dense import ChromaDenseStage
from app.retrieval.pipeline.stages.cross_encoder_rerank import CrossEncoderRerankStage
from app.retrieval.pipeline.stages.llm_relevance_filter import LLMRelevanceFilterStage
from app.retrieval.pipeline.stages.rrf_fusion import RRFFusionStage


@dataclass(frozen=True)
class PipelineSpec:
    pipeline_id: str
    seed: int
    stages: list[dict[str, Any]]
    final_top_k: int
    raw: dict[str, Any]
    source_path: Path | None = None

    @property
    def pipeline_hash(self) -> str:
        payload = json.dumps(self.raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True)
class PipelineResult:
    query: EvalQuery
    stage_outputs: dict[str, StageOutput]
    final_docs: list[RetrievedDoc]
    latency_ms: float


def load_pipeline_spec(path: str | Path) -> PipelineSpec:
    source_path = Path(path)
    with source_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    final = raw.get("final") or {}
    return PipelineSpec(
        pipeline_id=str(raw.get("pipeline_id") or source_path.stem),
        seed=int(raw.get("seed") or 42),
        stages=list(raw.get("stages") or []),
        final_top_k=int(final.get("take_top_k") or raw.get("take_top_k") or 10),
        raw=raw,
        source_path=source_path,
    )


class RetrievalPipelineRunner:
    def __init__(self, spec: PipelineSpec) -> None:
        self.spec = spec
        self.stages = [_build_stage(stage_spec) for stage_spec in spec.stages]

    async def run_query(self, query: EvalQuery) -> PipelineResult:
        current = StageInput(query=query)
        outputs: dict[str, StageOutput] = {}
        total_latency = 0.0

        for stage in self.stages:
            output = await stage.run(current)
            outputs[output.stage_name] = output
            total_latency += output.latency_ms
            current = StageInput(query=query, candidates=output.candidates, context={"stage_outputs": outputs})

        final_docs = list(current.candidates)[: self.spec.final_top_k]
        return PipelineResult(
            query=query,
            stage_outputs=outputs,
            final_docs=final_docs,
            latency_ms=total_latency,
        )

    async def run(self, queries: list[EvalQuery]) -> list[PipelineResult]:
        results: list[PipelineResult] = []
        for query in queries:
            results.append(await self.run_query(query))
        return results

    def run_sync(self, queries: list[EvalQuery]) -> list[PipelineResult]:
        return asyncio.run(self.run(queries))


def _build_stage(stage_spec: dict[str, Any]):
    stage_type = str(stage_spec.get("type") or "").strip()
    params = dict(stage_spec.get("params") or {})
    name = str(stage_spec.get("name") or stage_type)

    if stage_type == "chroma_dense":
        return ChromaDenseStage(
            name=name,
            collection=str(params.get("collection") or settings.DEFAULT_CHROMA_COLLECTION),
            top_k=int(params.get("top_k") or params.get("default_top_k") or 10),
            use_adaptive_router=bool(params.get("use_adaptive_router") or params.get("top_k_from_router")),
            snippet_max_chars=int(params.get("snippet_max_chars") or 140),
        )

    if stage_type == "cross_encoder_rerank":
        return CrossEncoderRerankStage(
            name=name,
            model_name=str(params.get("model_name") or "BAAI/bge-reranker-v2-m3"),
            top_k=int(params.get("top_k") or 10),
            batch_size=int(params.get("batch_size") or 32),
        )

    if stage_type == "bm25_retriever":
        return BM25RetrieveStage(
            name=name,
            collection=str(params.get("collection") or settings.DEFAULT_CHROMA_COLLECTION),
            top_k=int(params.get("top_k") or 50),
            index_dir=str(params.get("index_dir") or "data/bm25_index"),
            tokenizer=str(params.get("tokenizer") or "whitespace"),
        )

    if stage_type == "llm_relevance_filter":
        return LLMRelevanceFilterStage(
            name=name,
            model=params.get("model"),
            top_k=int(params.get("top_k") or 5),
            min_score=int(params.get("min_score") or 1),
            rerank_pool=int(params.get("rerank_pool") or 10),
            max_chars=int(params.get("max_chars") or 600),
            max_concurrency=int(params.get("max_concurrency") or 4),
        )

    if stage_type == "rrf_fusion":
        source_stages = params.get("source_stages")
        return RRFFusionStage(
            name=name,
            source_stages=list(source_stages) if source_stages else None,
            top_k=int(params.get("top_k") or 10),
            k=int(params.get("k") or 60),
        )

    raise ValueError(f"지원하지 않는 검색 단계 유형입니다: {stage_type}")

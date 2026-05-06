"""ir_measures 기반 검색 평가 메트릭 계산."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ir_measures import AP, MRR, P, Qrel, Recall, ScoredDoc, calc_aggregate, iter_calc, nDCG

from app.evaluation.datasets import QrelRecord


DEFAULT_METRICS = [Recall @ 5, Recall @ 10, P @ 5, MRR @ 5, MRR @ 10, nDCG @ 5, nDCG @ 10, AP @ 10]


@dataclass(frozen=True)
class RunRecord:
    qid: str
    docid: str
    score: float
    rank: int
    stage: str = "final"


def evaluate_run(
    qrels: Iterable[QrelRecord],
    run: Iterable[RunRecord],
    metrics: Iterable = DEFAULT_METRICS,
) -> dict[str, float]:
    results = calc_aggregate(list(metrics), _to_ir_qrels(qrels), _to_ir_run(run))
    return {str(metric): float(value) for metric, value in results.items()}


def per_query_metric(
    qrels: Iterable[QrelRecord],
    run: Iterable[RunRecord],
    metric=nDCG @ 10,
) -> dict[str, float]:
    rows = iter_calc([metric], _to_ir_qrels(qrels), _to_ir_run(run))
    return {str(row.query_id): float(row.value) for row in rows}


def _to_ir_qrels(qrels: Iterable[QrelRecord]) -> list[Qrel]:
    return [Qrel(qrel.qid, qrel.docid, int(qrel.relevance)) for qrel in qrels]


def _to_ir_run(run: Iterable[RunRecord]) -> list[ScoredDoc]:
    return [ScoredDoc(row.qid, row.docid, float(row.score)) for row in run]


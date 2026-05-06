"""System comparison helpers backed by ranx."""

from __future__ import annotations

from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord


def compare_runs(
    qrels: list[QrelRecord],
    runs: dict[str, list[RunRecord]],
    metrics: list[str] | None = None,
):
    """Return a ranx comparison report for named runs."""
    from ranx import Qrels, Run, compare

    qrels_payload: dict[str, dict[str, int]] = {}
    for qrel in qrels:
        qrels_payload.setdefault(qrel.qid, {})[qrel.docid] = int(qrel.relevance)

    ranx_runs = []
    for name, rows in runs.items():
        run_payload: dict[str, dict[str, float]] = {}
        for row in rows:
            run_payload.setdefault(row.qid, {})[row.docid] = float(row.score)
        ranx_runs.append(Run(run_payload, name=name))

    return compare(
        qrels=Qrels(qrels_payload),
        runs=ranx_runs,
        metrics=metrics or ["ndcg@10", "map@10", "mrr@10", "recall@10"],
        max_p=0.05,
    )


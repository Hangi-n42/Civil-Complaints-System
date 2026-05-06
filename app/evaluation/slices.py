"""검색 평가 메트릭의 slice별 집계."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.evaluation.datasets import EvalQuery, QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run


DEFAULT_SLICE_KEYS = ("scenario_type", "risk_level", "topic_type", "complexity_level")


def evaluate_slices(
    queries: Iterable[EvalQuery],
    qrels: list[QrelRecord],
    run: list[RunRecord],
    slice_keys: Iterable[str] = DEFAULT_SLICE_KEYS,
) -> dict[str, dict[str, dict[str, float | int]]]:
    query_by_id = {query.qid: query for query in queries}
    qrels_by_qid: dict[str, list[QrelRecord]] = defaultdict(list)
    run_by_qid: dict[str, list[RunRecord]] = defaultdict(list)
    for qrel in qrels:
        qrels_by_qid[qrel.qid].append(qrel)
    for row in run:
        run_by_qid[row.qid].append(row)

    output: dict[str, dict[str, dict[str, float | int]]] = {}
    for slice_key in slice_keys:
        groups: dict[str, list[str]] = defaultdict(list)
        for qid, query in query_by_id.items():
            group = str(query.metadata.get(slice_key) or "unknown").lower()
            groups[group].append(qid)

        output[slice_key] = {}
        for group, qids in groups.items():
            group_qrels = [row for qid in qids for row in qrels_by_qid.get(qid, [])]
            group_run = [row for qid in qids for row in run_by_qid.get(qid, [])]
            metrics = evaluate_run(group_qrels, group_run) if group_qrels and group_run else {}
            output[slice_key][group] = {
                "count": len(qids),
                **{metric: round(value, 4) for metric, value in metrics.items()},
            }
    return output


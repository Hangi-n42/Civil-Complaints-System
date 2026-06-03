from __future__ import annotations

import json

import pytest

from app.evaluation.artifacts import write_trec_run
from app.evaluation.datasets import QrelRecord, load_eval_dataset
from app.evaluation.metrics import RunRecord, evaluate_run
from app.evaluation.slices import evaluate_slices
from app.retrieval.pipeline.base import StageInput
from app.retrieval.pipeline.runner import load_pipeline_spec
from app.retrieval.pipeline.stages.chroma_dense import ChromaDenseStage


def test_beir_compatible_eval_dataset_loader(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "corpus.jsonl").write_text(
        json.dumps({"_id": "D1", "text": "BRT 노선 확장", "metadata": {"topic_type": "traffic"}}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (eval_dir / "queries.jsonl").write_text(
        json.dumps({"_id": "Q1", "text": "BRT 언제", "topic_type": "traffic"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (eval_dir / "qrels.tsv").write_text("qid\tdocid\trelevance\nQ1\tD1\t3\n", encoding="utf-8")

    dataset = load_eval_dataset(eval_dir)

    assert dataset.corpus[0].docid == "D1"
    assert dataset.queries[0].metadata["topic_type"] == "traffic"
    assert dataset.qrels == [QrelRecord("Q1", "D1", 3)]
    assert dataset.eval_set_hash.startswith("sha256:")


def test_ir_measures_based_core_metrics():
    qrels = [QrelRecord("Q1", "D1", 3), QrelRecord("Q1", "D3", 2), QrelRecord("Q1", "D5", 1)]
    run = [
        RunRecord("Q1", "D1", 5.0, 1),
        RunRecord("Q1", "D3", 4.0, 2),
        RunRecord("Q1", "D2", 3.0, 3),
        RunRecord("Q1", "D5", 2.0, 4),
    ]

    metrics = evaluate_run(qrels, run)

    assert metrics["R@5"] == pytest.approx(1.0)
    assert metrics["P@5"] == pytest.approx(0.6)
    assert metrics["RR@5"] == pytest.approx(1.0)
    assert "nDCG@5" in metrics


def test_trec_run_artifact_format(tmp_path):
    path = tmp_path / "run.trec"

    write_trec_run(path, [RunRecord("Q1", "D1", 2.5, 1)], run_name="test")

    assert path.read_text(encoding="utf-8").strip() == "Q1 Q0 D1 1 2.50000000 test"


def test_declarative_pipeline_spec_hash(tmp_path):
    spec_path = tmp_path / "pipeline.yaml"
    spec_path.write_text(
        """
pipeline_id: baseline_dense
seed: 42
stages:
  - name: dense_retriever
    type: chroma_dense
    params:
      collection: civil_cases_v1
      top_k: 10
final:
  take_top_k: 5
""",
        encoding="utf-8",
    )

    spec = load_pipeline_spec(spec_path)

    assert spec.pipeline_id == "baseline_dense"
    assert spec.final_top_k == 5
    assert spec.pipeline_hash.startswith("sha256:")


def test_slice_metrics_are_grouped_by_query_metadata():
    queries = [
        _query("Q1", {"topic_type": "traffic", "complexity_level": "high"}),
        _query("Q2", {"topic_type": "welfare", "complexity_level": "low"}),
    ]
    qrels = [QrelRecord("Q1", "D1", 1), QrelRecord("Q2", "D2", 1)]
    run = [RunRecord("Q1", "D1", 2.0, 1), RunRecord("Q2", "D3", 2.0, 1)]

    slices = evaluate_slices(queries, qrels, run, slice_keys=("topic_type", "complexity_level"))

    assert slices["topic_type"]["traffic"]["R@5"] == pytest.approx(1.0)
    assert slices["topic_type"]["welfare"]["R@5"] == pytest.approx(0.0)
    assert slices["complexity_level"]["high"]["count"] == 1


@pytest.mark.asyncio
async def test_chroma_dense_stage_uses_retrieval_service_adapter():
    service = _FakeRetrievalService()
    stage = ChromaDenseStage(name="dense_retriever", collection="civil_cases_v1", top_k=1, service=service)
    query = _query("Q1", {"topic_type": "traffic"})

    output = await stage.run(StageInput(query=query))

    assert output.stage_name == "dense_retriever"
    # #202 이후 평가 정답셋이 case 단위 → docid는 case_id 우선 (chunk_id 아님)
    assert output.candidates[0].docid == "C1"
    assert output.candidates[0].rank == 1
    assert service.calls[0]["query"] == "BRT 언제"


def _query(qid, metadata):
    from app.evaluation.datasets import EvalQuery

    return EvalQuery(qid=qid, text="BRT 언제", metadata=metadata)


class _FakeRetrievalService:
    def __init__(self):
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {
                "chunk_id": "D1",
                "score": 0.9,
                "rank": 1,
                "case_id": "C1",
                "metadata": {"source": "test"},
            }
        ]


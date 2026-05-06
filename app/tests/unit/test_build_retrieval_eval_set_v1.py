from __future__ import annotations

import json

from scripts.build_retrieval_eval_set_v1 import (
    convert_legacy_eval_set,
    write_eval_set,
    write_manifest,
    write_smoke_subset,
)


def test_convert_legacy_eval_set_builds_beir_rows():
    payload = [
        {
            "case_id": "CASE-001",
            "query": "도로 보수 요청",
            "scenario_type": "ops",
            "risk_level": "high",
            "topic_type": "traffic",
            "complexity_level": "high",
            "context": [
                {"chunk_id": "DOC-1", "chunk_text": "도로 보수 일정", "relevance": 3, "region": "서울"},
                {"chunk_id": "DOC-2", "chunk_text": "민원 접수 절차", "score": 0.61},
            ],
        }
    ]

    corpus, queries, qrels = convert_legacy_eval_set(payload)

    assert len(corpus) == 2
    assert queries[0]._id == "CASE-001"
    assert queries[0].metadata["topic_type"] == "traffic"
    assert {(row.docid, row.relevance) for row in qrels} == {("DOC-1", 3), ("DOC-2", 2)}


def test_write_eval_set_and_manifest(tmp_path):
    corpus, queries, qrels = convert_legacy_eval_set(
        [
            {
                "case_id": "CASE-001",
                "query": "가로등 점검",
                "context": [{"chunk_id": "DOC-1", "chunk_text": "가로등 고장 신고", "relevance": 3}],
            },
            {
                "case_id": "CASE-002",
                "query": "악취 신고",
                "context": [{"chunk_id": "DOC-2", "chunk_text": "악취 민원 처리", "relevance": 2}],
            },
        ]
    )
    output_dir = tmp_path / "eval" / "v1"
    source_path = tmp_path / "legacy_eval_set.json"
    source_path.write_text(json.dumps([{"case_id": "dummy"}], ensure_ascii=False), encoding="utf-8")

    write_eval_set(output_dir, corpus, queries, qrels)
    write_smoke_subset(output_dir / "smoke", queries, qrels, smoke_size=1)
    write_manifest(output_dir, source_path, corpus, queries, qrels, smoke_size=1)

    assert (output_dir / "corpus.jsonl").exists()
    assert (output_dir / "queries.jsonl").exists()
    assert (output_dir / "qrels.tsv").exists()
    assert (output_dir / "manifest.json").exists()

    smoke_qrels = (output_dir / "smoke" / "qrels.tsv").read_text(encoding="utf-8")
    assert "CASE-001" in smoke_qrels
    assert "CASE-002" not in smoke_qrels

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["queries"] == 2
    assert manifest["counts"]["smoke_size"] == 1
    assert manifest["files"]["qrels_tsv_sha256"].startswith("sha256:")


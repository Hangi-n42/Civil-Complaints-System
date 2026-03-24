from __future__ import annotations

from app.retrieval.vectorstores.chroma_validation import run_chromadb_filter_validation


def test_run_chromadb_filter_validation_passes(tmp_path):
    report = run_chromadb_filter_validation(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="test_week2_be2_filter_check",
        reset_collection=True,
    )

    assert report["status"] == "passed"
    assert report["collection_count"] >= 3
    assert {"category", "region", "created_at", "entity_labels"}.issubset(
        set(report["metadata_keys"])
    )
    assert all(item["passed"] for item in report["checks"])

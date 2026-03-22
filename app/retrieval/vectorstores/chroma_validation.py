"""ChromaDB 컬렉션/필터 점검 유틸리티."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings


def _build_sample_rows() -> List[Dict[str, Any]]:
    return [
        {
            "id": "CASE-2026-000101__chunk-0",
            "document": "강남구 가로등 점멸로 야간 보행이 위험합니다. 조명 점검을 요청합니다.",
            "embedding": [0.11, 0.21, 0.31, 0.41],
            "metadata": {
                "case_id": "CASE-2026-000101",
                "chunk_id": "CASE-2026-000101__chunk-0",
                "category": "도로안전",
                "region": "서울시 강남구",
                "created_at": "2026-03-19T20:10:00+09:00",
                "created_at_ts": 1742382600,
                "entity_labels": "FACILITY|HAZARD|TIME",
                "source": "aihub_71852",
            },
        },
        {
            "id": "CASE-2026-000102__chunk-0",
            "document": "서초구 공원 화장실 누수로 시설 이용이 어렵습니다. 긴급 보수를 요청합니다.",
            "embedding": [0.12, 0.22, 0.32, 0.42],
            "metadata": {
                "case_id": "CASE-2026-000102",
                "chunk_id": "CASE-2026-000102__chunk-0",
                "category": "시설관리",
                "region": "서울시 서초구",
                "created_at": "2026-03-20T09:00:00+09:00",
                "created_at_ts": 1742428800,
                "entity_labels": "FACILITY",
                "source": "aihub_71852",
            },
        },
        {
            "id": "CASE-2026-000103__chunk-0",
            "document": "강남구 버스정류장 바닥 파손으로 미끄럼 위험이 있습니다.",
            "embedding": [0.13, 0.23, 0.33, 0.43],
            "metadata": {
                "case_id": "CASE-2026-000103",
                "chunk_id": "CASE-2026-000103__chunk-0",
                "category": "도로안전",
                "region": "서울시 강남구",
                "created_at": "2026-03-21T07:35:00+09:00",
                "created_at_ts": 1742509950,
                "entity_labels": "FACILITY|HAZARD",
                "source": "aihub_71852",
            },
        },
    ]


def run_chromadb_filter_validation(
    persist_directory: Optional[str] = None,
    collection_name: str = "week2_be2_filter_check",
    reset_collection: bool = True,
) -> Dict[str, Any]:
    """ChromaDB 컬렉션 및 메타데이터 필터 동작을 점검한다."""
    report: Dict[str, Any] = {
        "status": "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "collection_name": collection_name,
        "persist_directory": persist_directory or settings.CHROMA_DB_PATH,
        "checks": [],
    }

    try:
        import chromadb
    except ImportError as exc:
        report["status"] = "skipped"
        report["reason"] = f"chromadb import 실패: {exc}"
        return report

    path = Path(report["persist_directory"])
    path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(path))
    if reset_collection:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(name=collection_name)

    rows = _build_sample_rows()
    existing = collection.count()
    if existing == 0:
        collection.add(
            ids=[row["id"] for row in rows],
            documents=[row["document"] for row in rows],
            embeddings=[row["embedding"] for row in rows],
            metadatas=[row["metadata"] for row in rows],
        )

    checks = [
        {
            "name": "filter_category_도로안전",
            "where": {"category": "도로안전"},
            "expected_min": 2,
        },
        {
            "name": "filter_region_서울시강남구",
            "where": {"region": "서울시 강남구"},
            "expected_min": 2,
        },
        {
            "name": "filter_created_at_exact",
            "where": {"created_at": "2026-03-20T09:00:00+09:00"},
            "expected_min": 1,
        },
        {
            "name": "filter_created_at_range_gte",
            "where": {"created_at_ts": {"$gte": 1742396400}},
            "expected_min": 2,
        },
        {
            "name": "filter_entity_labels_exact",
            "where": {"entity_labels": "FACILITY|HAZARD"},
            "expected_min": 1,
        },
    ]

    result_checks: List[Dict[str, Any]] = []
    for check in checks:
        rows = collection.get(where=check["where"], include=["metadatas"])
        actual_count = len(rows.get("ids", []))
        result_checks.append(
            {
                "name": check["name"],
                "where": check["where"],
                "expected_min": check["expected_min"],
                "actual_count": actual_count,
                "passed": actual_count >= check["expected_min"],
            }
        )

    report["collection_count"] = collection.count()
    report["checks"] = result_checks
    report["status"] = "passed" if all(item["passed"] for item in result_checks) else "failed"
    report["metadata_keys"] = sorted(
        {
            key
            for row in _build_sample_rows()
            for key in row["metadata"].keys()
        }
    )
    return report

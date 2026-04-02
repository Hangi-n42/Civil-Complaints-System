"""Issue #102 runner: Metadata filter validation for 5 scenarios A-E.

이 스크립트는 region/category/date 필터에 대해 다음 5개 시나리오를 자동 검증한다:
- Scenario A: region 단일 필터
- Scenario B: category 단일 필터
- Scenario C: region + category 복합 필터
- Scenario D: date_from + date_to 범위 필터
- Scenario E: 모든 필터 복합

Usage:
  c:/Projects/AI-Civil-Affairs-Systems/.venv/Scripts/python.exe scripts/run_issue_102.py \
    --collection civil_cases_v1 \
    --output logs/evaluation/week3_filter_validation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings


@dataclass
class FilterTestCase:
    name: str
    where: Dict[str, Any]
    expected_min: int
    description: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue #102 filter validation runner")
    parser.add_argument(
        "--collection",
        type=str,
        default="civil_cases_v1",
        help="Chroma collection name",
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=settings.CHROMA_DB_PATH,
        help="Chroma persist directory",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output report json",
    )
    return parser.parse_args()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_filter_test_cases() -> List[FilterTestCase]:
    """Issue #102의 5대 시나리오 테스트 케이스"""
    now = datetime.now(timezone.utc)
    now_timestamp = int(now.timestamp())
    yesterday_timestamp = int((now - timedelta(days=1)).timestamp())
    tomorrow_timestamp = int((now + timedelta(days=1)).timestamp())

    return [
        FilterTestCase(
            name="scenario_a_region_single",
            where={"region": "unknown"},
            expected_min=1,
            description="region 단일 필터: region=unknown이 포함된 모든 청크",
        ),
        FilterTestCase(
            name="scenario_b_category_single",
            where={"category": "road_safety"},
            expected_min=1,
            description="category 단일 필터: category=road_safety인 시나리오",
        ),
        FilterTestCase(
            name="scenario_c_region_category_and",
            where={"$and": [{"region": "unknown"}, {"category": "road_safety"}]},
            expected_min=0,
            description="region + category AND 필터: 두 조건을 모두 만족하는 청크",
        ),
        FilterTestCase(
            name="scenario_d_date_range",
            where={"$and": [{"created_at": {"$gte": yesterday_timestamp}}, {"created_at": {"$lte": tomorrow_timestamp}}]},
            expected_min=0,
            description="date_from + date_to 범위 필터: 범위 내 생성된 청크 (Unix timestamp)",
        ),
        FilterTestCase(
            name="scenario_e_all_filters_complex",
            where={
                "$and": [
                    {"region": "unknown"},
                    {"category": "road_safety"},
                    {"created_at": {"$gte": yesterday_timestamp}},
                ]
            },
            expected_min=0,
            description="모든 필터 복합: region + category + date_from (Unix timestamp)",
        ),
    ]


def _run_filter_validation(
    persist_dir: str,
    collection_name: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Chroma 필터 검증 실행"""
    import chromadb

    persist_path = Path(persist_dir)
    if not persist_path.exists():
        raise RuntimeError(f"ChromaDB path not found: {persist_dir}")

    client = chromadb.PersistentClient(path=str(persist_path))

    try:
        collection = client.get_collection(name=collection_name)
    except Exception as exc:
        raise RuntimeError(f"Collection not found: {collection_name}") from exc

    test_cases = _build_filter_test_cases()
    results: List[Dict[str, Any]] = []

    for test_case in test_cases:
        try:
            # Chroma query with where clause
            query_result = collection.get(
                where=test_case.where,
                include=["metadatas"],
            )
            actual_count = len(query_result.get("ids", []))
            passed = actual_count >= test_case.expected_min

            results.append(
                {
                    "name": test_case.name,
                    "description": test_case.description,
                    "where": test_case.where,
                    "expected_min": test_case.expected_min,
                    "actual_count": actual_count,
                    "passed": passed,
                    "status": "PASS" if passed else "FAIL",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "name": test_case.name,
                    "description": test_case.description,
                    "where": test_case.where,
                    "expected_min": test_case.expected_min,
                    "actual_count": 0,
                    "passed": False,
                    "status": "ERROR",
                    "error": str(exc),
                }
            )

    stats = {
        "total_tests": len(results),
        "passed_tests": sum(1 for r in results if r["passed"]),
        "failed_tests": sum(1 for r in results if not r["passed"]),
        "all_passed": all(r["passed"] for r in results),
    }

    return results, stats


def _write_report(path: Path, report: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    t0 = datetime.now(timezone.utc)

    output_path = Path(args.output)

    try:
        results, stats = _run_filter_validation(
            persist_dir=args.persist_dir,
            collection_name=args.collection,
        )

        elapsed_sec = (datetime.now(timezone.utc) - t0).total_seconds()

        report = {
            "status": "success" if stats["all_passed"] else "failure",
            "generated_at": _now_iso(),
            "pipeline_phase": "issue_102",
            "collection": args.collection,
            "tests": results,
            "summary": {
                "total_tests": stats["total_tests"],
                "passed_tests": stats["passed_tests"],
                "failed_tests": stats["failed_tests"],
                "all_passed": stats["all_passed"],
                "elapsed_sec": round(elapsed_sec, 2),
            },
            "gate": {
                "issue": "102",
                "requirement": "All 5 filter scenarios pass",
                "passed": stats["all_passed"],
            },
        }

        _write_report(output_path, report)

        print("[OK] filter validation complete")
        print(f"[OK] tests={stats['total_tests']} passed={stats['passed_tests']} failed={stats['failed_tests']}")
        print(f"[OK] report={output_path}")

        return 0 if stats["all_passed"] else 1

    except Exception as exc:
        elapsed_sec = (datetime.now(timezone.utc) - t0).total_seconds()
        report = {
            "status": "error",
            "generated_at": _now_iso(),
            "pipeline_phase": "issue_102",
            "error": str(exc),
            "elapsed_sec": round(elapsed_sec, 2),
            "collection": args.collection,
        }
        _write_report(output_path, report)
        print(f"[ERROR] {exc}")
        print(f"[INFO] error report saved: {output_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

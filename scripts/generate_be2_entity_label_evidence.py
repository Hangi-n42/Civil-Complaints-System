"""BE2 entity_labels 계약 검증 및 증빙 산출물 생성 스크립트."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List

from fastapi.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.api.main import app
from app.api.routers import retrieval as retrieval_router
from app.retrieval.service import RetrievalService


def _sample_records() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "CASE-2026-900001",
            "created_at": "2026-03-20T09:10:00+09:00",
            "source": "aihub_71852",
            "category": "도로안전",
            "region": "서울시 강남구",
            "text": "강남구 사거리 가로등이 고장나 위험합니다.",
            "entities": [
                {"label": "FACILITY", "text": "가로등"},
                {"label": "HAZARD", "text": "위험"},
            ],
        },
        {
            "case_id": "CASE-2026-900002",
            "created_at": "2026-03-20T09:20:00+09:00",
            "source": "aihub_71852",
            "category": "시설관리",
            "region": "서울시 서초구",
            "text": "공원 화장실 누수로 시설 이용이 어렵습니다.",
            "entities": [
                {"label": "FACILITY", "text": "화장실"},
                {"label": "TYPE", "text": "비표준"},
            ],
        },
        {
            "case_id": "CASE-2026-900003",
            "created_at": "2026-03-20T09:30:00+09:00",
            "source": "aihub_71852",
            "category": "도로안전",
            "region": "서울시 강남구",
            "text": "버스정류장 바닥 파손으로 전도 위험이 있습니다.",
            "entities": [
                {"label": "FACILITY", "text": "버스정류장"},
                {"label": "HAZARD", "text": "전도 위험"},
            ],
        },
        {
            "case_id": "CASE-2026-900004",
            "created_at": "2026-03-20T09:40:00+09:00",
            "source": "aihub_71852",
            "category": "치안",
            "region": "서울시 강북구",
            "text": "야간 골목 조도가 낮아 순찰이 필요합니다.",
            "entities": [{"label": "LOCATION", "text": "골목"}],
        },
        {
            "case_id": "CASE-2026-900005",
            "created_at": "2026-03-20T09:50:00+09:00",
            "source": "aihub_71852",
            "category": "시설관리",
            "region": "서울시 강동구",
            "text": "체육시설 배수구 막힘으로 악취가 발생합니다.",
            "entities": [
                {"label": "FACILITY", "text": "체육시설"},
                {"label": "TIME", "text": "주말 저녁"},
            ],
        },
        {
            "case_id": "CASE-2026-900006",
            "created_at": "2026-03-20T10:00:00+09:00",
            "source": "aihub_71852",
            "category": "도로안전",
            "region": "서울시 강남구",
            "text": "신호등 주변 보행로 파손으로 안전사고 우려가 큽니다.",
            "entities": [
                {"label": "FACILITY", "text": "보행로"},
                {"label": "HAZARD", "text": "안전사고 우려"},
                {"label": "TIME", "text": "출근 시간"},
            ],
        },
        {
            "case_id": "CASE-2026-900007",
            "created_at": "2026-03-20T10:10:00+09:00",
            "source": "aihub_71852",
            "category": "환경",
            "region": "서울시 마포구",
            "text": "하천변 쓰레기 적치로 악취가 발생합니다.",
            "entities": [{"label": "LOCATION", "text": "하천변"}],
        },
        {
            "case_id": "CASE-2026-900008",
            "created_at": "2026-03-20T10:20:00+09:00",
            "source": "aihub_71852",
            "category": "시설관리",
            "region": "서울시 강서구",
            "text": "복지관 엘리베이터 잦은 고장으로 이용 불편이 큽니다.",
            "entities": [
                {"label": "FACILITY", "text": "엘리베이터"},
                {"label": "ADMIN_UNIT", "text": "강서구"},
            ],
        },
        {
            "case_id": "CASE-2026-900009",
            "created_at": "2026-03-20T10:30:00+09:00",
            "source": "aihub_71852",
            "category": "도로안전",
            "region": "서울시 성북구",
            "text": "횡단보도 턱이 높아 휠체어 이동이 어렵습니다.",
            "entities": [{"label": "FACILITY", "text": "횡단보도"}],
        },
        {
            "case_id": "CASE-2026-900010",
            "created_at": "2026-03-20T10:40:00+09:00",
            "source": "aihub_71852",
            "category": "도로안전",
            "region": "서울시 강남구",
            "text": "야간 공사 구간 안전 펜스가 없어 위험합니다.",
            "entities": [
                {"label": "HAZARD", "text": "위험"},
                {"label": "TIME", "text": "야간"},
                {"label": "TYPE", "text": "비표준"},
            ],
        },
    ]


async def _build_service() -> RetrievalService:
    service = RetrievalService()
    await service.index_documents(_sample_records(), rebuild=True)
    return service


def _build_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# BE2 entity_labels 통합 검증 결과")
    lines.append("")
    lines.append(f"- generated_at: {report['generated_at']}")
    lines.append("")

    lines.append("## 1) 인덱스 저장 샘플 10건")
    lines.append("")
    lines.append("| case_id | entity_labels |")
    lines.append("| --- | --- |")
    for row in report["index_entity_labels_sample"]:
        labels = ", ".join(row["entity_labels"])
        lines.append(f"| {row['case_id']} | {labels} |")

    lines.append("")
    lines.append("## 2) 검색 요청/응답 로그 5세트")
    lines.append("")
    for item in report["search_logs"]:
        lines.append(f"### {item['name']}")
        lines.append(f"- status_code: {item['status_code']}")
        lines.append(f"- request: {json.dumps(item['request'], ensure_ascii=False)}")
        lines.append(f"- response_excerpt: {json.dumps(item['response_excerpt'], ensure_ascii=False)}")
        lines.append("")

    lines.append("## 3) 필터 적용 전후 결과 건수 비교")
    lines.append("")
    lines.append("| scenario | before_count | after_count | took_ms |")
    lines.append("| --- | ---: | ---: | ---: |")
    for row in report["before_after_count_table"]:
        before_count = "-" if row["before_count"] is None else str(row["before_count"])
        after_count = "-" if row["after_count"] is None else str(row["after_count"])
        lines.append(f"| {row['scenario']} | {before_count} | {after_count} | {row['took_ms']} |")

    lines.append("")
    lines.append("## 4) 오류 처리 정책 적용 캡처")
    lines.append("")
    lines.append("- 정책: 비표준 라벨 입력 시 422 반환(무시하지 않음)")
    lines.append(f"- invalid_label_response: {json.dumps(report['invalid_label_response'], ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def main(output_dir: Path) -> int:
    service = asyncio.run(_build_service())

    retrieval_router.get_retrieval_service = lambda: service
    client = TestClient(app)

    scenarios = [
        {
            "name": "단일 라벨 필터 FACILITY",
            "request": {
                "query": "위험",
                "top_k": 5,
                "filters": {"entity_labels": ["FACILITY"]},
            },
        },
        {
            "name": "복수 라벨 필터 FACILITY+HAZARD",
            "request": {
                "query": "위험",
                "top_k": 5,
                "filters": {"entity_labels": ["FACILITY", "HAZARD"]},
            },
        },
        {
            "name": "존재하지 않는 라벨 입력 ADMIN_UNIT",
            "request": {
                "query": "위험",
                "top_k": 5,
                "filters": {"entity_labels": ["ADMIN_UNIT"]},
            },
        },
        {
            "name": "비표준 라벨 입력 TYPE",
            "request": {
                "query": "위험",
                "top_k": 5,
                "filters": {"entity_labels": ["TYPE"]},
            },
        },
        {
            "name": "entity_labels 미전달",
            "request": {
                "query": "위험",
                "top_k": 5,
            },
        },
    ]

    logs: List[Dict[str, Any]] = []
    compare_rows: List[Dict[str, Any]] = []
    invalid_response: Dict[str, Any] = {}

    for scenario in scenarios:
        request_body = scenario["request"]

        before_count = None
        if "filters" in request_body and "entity_labels" in request_body["filters"]:
            before_req = {
                "query": request_body["query"],
                "top_k": request_body.get("top_k", 5),
            }
            before_res = client.post("/api/v1/search", json=before_req)
            if before_res.status_code == 200:
                before_count = before_res.json().get("data", {}).get("count")

        started = perf_counter()
        response = client.post("/api/v1/search", json=request_body)
        took_ms = int((perf_counter() - started) * 1000)

        response_body = response.json()
        if response.status_code == 200:
            data = response_body.get("data", {})
            top_results = [
                {
                    "chunk_id": item.get("chunk_id"),
                    "case_id": item.get("case_id"),
                    "score": item.get("score"),
                }
                for item in data.get("results", [])[:3]
            ]
            response_excerpt = {
                "count": data.get("count"),
                "took_ms": data.get("took_ms"),
                "top_results": top_results,
            }
            after_count = data.get("count")
        else:
            response_excerpt = response_body
            after_count = None

        if scenario["name"] == "비표준 라벨 입력 TYPE":
            invalid_response = {
                "status_code": response.status_code,
                "body": response_body,
            }

        logs.append(
            {
                "name": scenario["name"],
                "status_code": response.status_code,
                "request": request_body,
                "response_excerpt": response_excerpt,
            }
        )

        compare_rows.append(
            {
                "scenario": scenario["name"],
                "before_count": before_count,
                "after_count": after_count,
                "took_ms": took_ms,
            }
        )

    index_labels_sample = [
        {
            "case_id": item.get("case_id"),
            "entity_labels": item.get("entity_labels", []),
        }
        for item in service._indexed_chunks[:10]
    ]

    report = {
        "generated_at": datetime_now_iso(),
        "index_entity_labels_sample": index_labels_sample,
        "search_logs": logs,
        "before_after_count_table": compare_rows,
        "invalid_label_response": invalid_response,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "be2_entity_label_evidence.json"
    md_path = output_dir / "be2_entity_label_evidence.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(report), encoding="utf-8")

    print(str(json_path))
    print(str(md_path))
    return 0


def datetime_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BE2 entity_labels 증빙 생성")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="docs/40_delivery/week2/artifacts",
        help="증빙 출력 디렉터리",
    )
    args = parser.parse_args()

    raise SystemExit(main(Path(args.output_dir)))

"""BE1 재구조화 컬렉션 검색 smoke 검증.

민원 원문과 snippet은 리포트에 쓰지 않고, 질의별 결과 ID와 metadata 신호만
남긴다. 산출물은 한국어 요약 기준으로 작성한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.retrieval.service import get_retrieval_service


DEFAULT_QUERIES = [
    "공연 예매 취소가 안 됩니다",
    "임금체불 신고와 퇴직금 지급 문의",
    "건설공사 하도급 대금 문제",
    "도로 파손으로 차량 통행이 위험합니다",
    "전세보증금 반환 관련 상담",
]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _split_pipe(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = value.split("|")
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []

    values: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = _clean(item)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        values.append(text)
    return values


def _compact_result(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {
        "rank": int(item.get("rank") or 0),
        "case_id": _clean(item.get("case_id")),
        "chunk_id": _clean(item.get("chunk_id")),
        "score": round(float(item.get("score") or 0.0), 6),
        "entity_texts": _split_pipe(metadata.get("entity_texts")),
        "legal_ref_names": _split_pipe(metadata.get("legal_ref_names")),
        "responsible_units_source": _clean(metadata.get("responsible_units_source")),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# BE1 재구조화 컬렉션 검색 Smoke 검증",
        "",
        f"- 생성 시각(UTC): `{report['generated_at']}`",
        f"- 컬렉션: `{report['collection']}`",
        f"- 질의 수: {len(report['queries'])}",
        f"- 빈 결과 질의 수: {report['empty_result_count']}",
        "",
        "## 질의별 결과",
        "",
    ]

    for query in report["queries"]:
        lines += [
            f"### {query['query']}",
            "",
            "| 순위 | case_id | 점수 | entity_texts 수 | legal_refs 수 | 부서 출처 |",
            "| ---: | --- | ---: | ---: | ---: | --- |",
        ]
        if not query["results"]:
            lines += ["| - | 결과 없음 | 0 | 0 | 0 | - |", ""]
            continue
        for row in query["results"]:
            lines.append(
                f"| {row['rank']} | `{row['case_id']}` | {row['score']:.4f} | "
                f"{len(row['entity_texts'])} | "
                f"{len(row['legal_ref_names'])} | `{row['responsible_units_source'] or '-'}` |"
            )
        lines.append("")

    lines += [
        "## 판단 기준",
        "",
        "- 빈 결과가 없어야 한다.",
        "- `entity_texts`, `legal_refs`, `responsible_units_source`가 검색 결과 metadata에서 읽혀야 한다.",
        "- 이 리포트는 민원 원문과 검색 snippet을 포함하지 않는다.",
        "",
    ]
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> None:
    service = get_retrieval_service()
    queries = args.query or DEFAULT_QUERIES
    report_queries = []

    for query in queries:
        results = await service.search(
            query,
            top_k=args.top_k,
            collection_name=args.collection,
            strategy=args.strategy,
            grounding_filter=False,
        )
        report_queries.append(
            {
                "query": query,
                "results": [_compact_result(item) for item in results],
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "top_k": args.top_k,
        "strategy": args.strategy,
        "empty_result_count": sum(1 for item in report_queries if not item["results"]),
        "queries": report_queries,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(_render_markdown(report), encoding="utf-8")
    print(f"[JSON] {args.out_json}")
    print(f"[Markdown] {args.out_md}")


def main() -> None:
    parser = argparse.ArgumentParser(description="BE1 재구조화 컬렉션 검색 smoke 검증")
    parser.add_argument("--collection", default="civil_cases_be1_restructured_v1")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--strategy", default="dense", choices=("dense", "hybrid"))
    parser.add_argument("--query", action="append", help="추가/대체 질의. 여러 번 지정 가능")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "reports" / "retrieval" / "v3" / "be1_restructured_search_smoke.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "reports" / "retrieval" / "v3" / "be1_restructured_search_smoke.md",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

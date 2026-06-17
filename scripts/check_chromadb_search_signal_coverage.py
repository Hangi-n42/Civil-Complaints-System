"""ChromaDB BE1 검색 신호 metadata 적재율을 점검한다.

이 스크립트는 읽기 전용이다. 민감할 수 있는 `entity_texts`, `key_terms` 값은
기본 리포트에 원문으로 쓰지 않고 sha256 prefix만 남긴다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings

FIELDS = [
    "entity_texts",
    "legal_ref_names",
    "legal_ref_ids",
    "key_terms",
    "responsible_units",
    "responsible_units_source",
    "urgency_level",
]
SENSITIVE_FIELDS = {"entity_texts", "key_terms"}


def _split_values(value: Any) -> list[str]:
    if value is None:
        raw_values = []
    elif isinstance(value, str):
        raw_values = value.split("|")
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]

    values: list[str] = []
    seen = set()
    for item in raw_values:
        text = " ".join(str(item or "").split())
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            values.append(text)
    return values


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def analyze_metadatas(
    metadatas: list[dict[str, Any] | None],
    *,
    total_count: int,
    top_n: int = 10,
) -> dict[str, Any]:
    scanned_count = len(metadatas)
    fields: dict[str, Any] = {}

    for field in FIELDS:
        present = 0
        values: Counter[str] = Counter()
        hashes: Counter[str] = Counter()

        for metadata in metadatas:
            field_values = _split_values((metadata or {}).get(field))
            if not field_values:
                continue
            present += 1
            values.update(field_values)
            hashes.update(_hash(value) for value in field_values)

        stat = {
            "present_count": present,
            "empty_count": scanned_count - present,
            "coverage_ratio": round(present / scanned_count, 6) if scanned_count else 0.0,
            "unique_value_count": len(values),
        }
        if field in SENSITIVE_FIELDS:
            stat["top_value_hashes"] = [
                {"sha256_12": value_hash, "count": count}
                for value_hash, count in hashes.most_common(top_n)
            ]
            stat["value_redaction"] = "원문 값 비노출"
        else:
            stat["top_values"] = [
                {"value": value, "count": count}
                for value, count in values.most_common(top_n)
            ]
        fields[field] = stat

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": total_count,
        "scanned_count": scanned_count,
        "limited": scanned_count < total_count,
        "fields": fields,
    }


def render_markdown(report: dict[str, Any], *, collection: str, persist_dir: str) -> str:
    fields = report["fields"]
    lines = [
        "# ChromaDB 검색 신호 metadata 적재율 점검",
        "",
        f"- 생성 시각(UTC): `{report['generated_at']}`",
        f"- persist dir: `{persist_dir}`",
        f"- collection: `{collection}`",
        f"- 전체 건수: {report['total_count']}",
        f"- 점검 건수: {report['scanned_count']}",
        f"- 제한 실행 여부: {'예' if report['limited'] else '아니오'}",
        "",
        "## 필드별 적재율",
        "",
        "| 필드 | 적재 건수 | 빈 값 건수 | 적재율 | 고유 값 수 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]

    for field in FIELDS:
        stat = fields[field]
        lines.append(
            f"| `{field}` | {stat['present_count']} | {stat['empty_count']} | "
            f"{stat['coverage_ratio'] * 100:.2f}% | {stat['unique_value_count']} |"
        )

    lines += [
        "",
        "## 상위 값 분포",
        "",
        "`entity_texts`, `key_terms`는 원문 값을 숨기고 해시 prefix만 표시한다.",
        "",
    ]

    for field in FIELDS:
        stat = fields[field]
        lines += [f"### `{field}`", ""]
        rows = stat.get("top_values") or stat.get("top_value_hashes") or []
        if not rows:
            lines += ["값 없음", ""]
            continue
        if "top_values" in stat:
            lines += ["| 값 | 건수 |", "| --- | ---: |"]
            lines += [f"| `{row['value']}` | {row['count']} |" for row in rows]
        else:
            lines += ["| sha256 prefix | 건수 |", "| --- | ---: |"]
            lines += [f"| `{row['sha256_12']}` | {row['count']} |" for row in rows]
        lines.append("")

    lines += [
        "## 해석 기준",
        "",
        "- `responsible_units` 적재율이 낮으면 BE1 설정과 인덱싱 경로를 먼저 확인한다.",
        "- `legal_ref_ids`와 `legal_ref_names` 적재율 차이가 크면 법령명과 law_id 매핑을 점검한다.",
        "- 이 스크립트는 ChromaDB metadata를 수정하지 않는다.",
        "- 민원 원문, 검색 snippet, 생성 답변 미리보기는 리포트에 포함하지 않는다.",
        "",
    ]
    return "\n".join(lines)


def collect_metadatas(collection: Any, *, limit: int, batch_size: int) -> tuple[int, list[dict[str, Any] | None]]:
    total = int(collection.count())
    scan_count = min(total, limit) if limit else total
    metadatas: list[dict[str, Any] | None] = []
    for offset in range(0, scan_count, batch_size):
        got = collection.get(
            limit=min(batch_size, scan_count - offset),
            offset=offset,
            include=["metadatas"],
        )
        metadatas.extend(got.get("metadatas") or [])
    return total, metadatas


def main() -> int:
    parser = argparse.ArgumentParser(description="ChromaDB 검색 신호 metadata 적재율 점검")
    parser.add_argument("--persist-dir", default=settings.CHROMA_DB_PATH)
    parser.add_argument("--collection", default="civil_cases_v1")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체 collection 점검")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument(
        "--out-json",
        default=str(Path("reports/retrieval/v3/chromadb_search_signal_metadata_coverage.json")),
    )
    parser.add_argument(
        "--out-md",
        default=str(Path("reports/retrieval/v3/chromadb_search_signal_metadata_coverage.md")),
    )
    args = parser.parse_args()

    import chromadb

    client = chromadb.PersistentClient(path=str(args.persist_dir))
    collection = client.get_collection(args.collection)
    total, metadatas = collect_metadatas(
        collection,
        limit=max(0, args.limit),
        batch_size=max(1, args.batch_size),
    )
    report = analyze_metadatas(metadatas, total_count=total, top_n=max(1, args.top_n))

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(
        render_markdown(report, collection=args.collection, persist_dir=str(args.persist_dir)),
        encoding="utf-8",
    )
    print(f"[JSON] {out_json}")
    print(f"[Markdown] {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

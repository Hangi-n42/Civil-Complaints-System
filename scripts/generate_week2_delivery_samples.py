"""Generate Week 2 delivery sample JSON records.

This script reads AIHub raw source files, normalizes them to the
BE1->BE2 delivery contract, and writes 20 sample records by default.

Usage:
    python scripts/generate_week2_delivery_samples.py
    python scripts/generate_week2_delivery_samples.py --count 20 --output data/samples/week2_delivery_sample_20.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from app.structuring.preprocessing import to_structuring_record


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = PROJECT_ROOT / "data" / "Training" / "01.원천데이터"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "samples" / "week2_delivery_sample_20.json"


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_record_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.rglob("*.json") if p.is_file()])


def as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_record(raw: Dict[str, Any], source_file: Path) -> Dict[str, Any]:
    source_id = str(raw.get("source_id") or "").strip()
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    structuring_record = to_structuring_record(raw)

    case_id = str(raw.get("case_id") or source_id or raw.get("id") or "").strip()
    if not case_id:
        return {}

    source = str(raw.get("source") or metadata.get("source") or "unknown").strip() or "unknown"
    created_at = (
        str(structuring_record.get("created_at") or raw.get("created_at") or raw.get("consulting_date") or "")
        .strip()
        or "unknown"
    )

    category = str(structuring_record.get("category") or raw.get("category") or "unknown").strip() or "unknown"
    if category == "-":
        category = "unknown"

    region = str(structuring_record.get("region") or raw.get("region") or "unknown").strip() or "unknown"

    # 샘플 계약도 운영과 동일하게 전처리 어댑터의 검색용 본문을 사용한다.
    if raw.get("consulting_content"):
        # 원천 상담 본문은 전처리 어댑터 결과를 우선해 Q/A 형식 흔들림을 정규화한다.
        raw_text = str(
            structuring_record.get("text") or raw.get("raw_text") or raw.get("text") or ""
        ).strip()
    else:
        # 이미 구조화 입력으로 정제된 레코드는 기존 raw_text/text 우선순위를 유지한다.
        raw_text = str(
            raw.get("raw_text") or raw.get("text") or structuring_record.get("text") or ""
        ).strip()

    result: Dict[str, Any] = {
        "case_id": case_id,
        "source": source,
        "created_at": created_at,
        "category": category,
        "region": region,
        "raw_text": raw_text,
        "entities": [],
        "metadata": {
            "source_id": source_id,
            "consulting_category": str(raw.get("consulting_category") or category),
            "consulting_turns": as_int(raw.get("consulting_turns")),
            "consulting_length": as_int(raw.get("consulting_length")),
            "client_gender": str(raw.get("client_gender") or ""),
            "client_age": str(raw.get("client_age") or ""),
            "source_file": str(source_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        },
    }

    return result


def collect_samples(count: int) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []

    for path in iter_record_files(RAW_ROOT):
        try:
            payload = load_json_file(path)
        except Exception:
            continue

        if not isinstance(payload, list):
            continue

        for row in payload:
            if not isinstance(row, dict):
                continue
            normalized = normalize_record(row, path)
            if not normalized:
                continue
            samples.append(normalized)
            if len(samples) >= count:
                return samples

    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Week 2 delivery sample JSON")
    parser.add_argument("--count", type=int, default=20, help="Number of records to export")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    args = parser.parse_args()

    samples = collect_samples(args.count)
    if len(samples) < args.count:
        print(f"Warning: requested {args.count}, collected {len(samples)} records")

    output_path = args.output
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "generated_at": __import__("datetime").datetime.now().isoformat(),
                    "count": len(samples),
                    "contract": "week2_be1_to_be2_delivery_v1",
                },
                "records": samples,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Wrote {len(samples)} records to: {output_path}")


if __name__ == "__main__":
    main()

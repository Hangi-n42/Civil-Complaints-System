"""Generate Week 2 delivery sample JSON records.

This script reads AIHub raw source files and optional labeling files,
normalizes them to the BE1->BE2 Week 2 delivery contract,
and writes 20 sample records by default.

Usage:
    python scripts/generate_week2_delivery_samples.py
    python scripts/generate_week2_delivery_samples.py --count 20 --output data/samples/week2_delivery_sample_20.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = PROJECT_ROOT / "data" / "Training" / "01.원천데이터"
LABEL_ROOT = PROJECT_ROOT / "data" / "Training" / "02.라벨링데이터"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "samples" / "week2_delivery_sample_20.json"


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_record_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.rglob("*.json") if p.is_file()])


def build_supervision_index(label_root: Path) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}

    for path in iter_record_files(label_root):
        try:
            payload = load_json_file(path)
        except Exception:
            continue

        if not isinstance(payload, list):
            continue

        for row in payload:
            if not isinstance(row, dict):
                continue

            source_id = str(row.get("source_id") or "").strip()
            if not source_id:
                continue

            slot = index.setdefault(source_id, {})
            instructions = row.get("instructions")
            if not isinstance(instructions, list):
                continue

            for ins in instructions:
                if not isinstance(ins, dict):
                    continue
                tuning_type = str(ins.get("tuning_type") or "").strip()
                data_rows = ins.get("data")
                if not isinstance(data_rows, list):
                    continue

                if tuning_type == "질의응답":
                    qa_bucket = slot.setdefault("qa", [])
                    for d in data_rows:
                        if not isinstance(d, dict):
                            continue
                        qa_bucket.append(
                            {
                                "task_category": str(d.get("task_category") or ""),
                                "instruction": str(d.get("instruction") or ""),
                                "question": str(d.get("instruction") or ""),
                                "answer": str(d.get("output") or ""),
                            }
                        )
                elif tuning_type == "요약" and data_rows:
                    d = data_rows[0]
                    if isinstance(d, dict):
                        slot["summary"] = {
                            "task_category": str(d.get("task_category") or ""),
                            "instruction": str(d.get("instruction") or ""),
                            "input": str(d.get("input") or ""),
                            "output": str(d.get("output") or ""),
                        }
                elif tuning_type == "분류" and data_rows:
                    d = data_rows[0]
                    if isinstance(d, dict):
                        slot["classification"] = {
                            "task_category": str(d.get("task_category") or ""),
                            "instruction": str(d.get("instruction") or ""),
                            "input": str(d.get("input") or ""),
                            "output": str(d.get("output") or ""),
                        }

    return index


def as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_record(raw: Dict[str, Any], supervision_map: Dict[str, Dict[str, Any]], source_file: Path) -> Dict[str, Any]:
    source_id = str(raw.get("source_id") or "").strip()
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}

    case_id = str(raw.get("case_id") or source_id or raw.get("id") or "").strip()
    if not case_id:
        return {}

    source = str(raw.get("source") or metadata.get("source") or "unknown").strip() or "unknown"
    created_at = str(raw.get("created_at") or raw.get("consulting_date") or "").strip() or "unknown"

    category = str(raw.get("category") or raw.get("consulting_category") or "unknown").strip() or "unknown"
    if category == "-":
        category = "unknown"

    region = str(raw.get("region") or "unknown").strip() or "unknown"

    raw_text = str(raw.get("raw_text") or raw.get("text") or raw.get("consulting_content") or "").strip()

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

    if source_id and source_id in supervision_map:
        result["supervision"] = supervision_map[source_id]

    return result


def collect_samples(count: int) -> List[Dict[str, Any]]:
    supervision_map = build_supervision_index(LABEL_ROOT)
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
            normalized = normalize_record(row, supervision_map, path)
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

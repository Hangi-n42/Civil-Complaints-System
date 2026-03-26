"""Run Week 2 BE1 end-to-end pipeline.

Flow:
1) Load records (supports list, {records: [...]}, {data: [...]})
2) Ingestion clean + PII masking + deduplication
3) Structuring (4 fields + entities + validation)
4) Write structured output + summary JSON
5) Optional evaluation report against gold annotations

Usage:
  python scripts/run_week2_be1_e2e.py
  python scripts/run_week2_be1_e2e.py --input data/samples/week2_delivery_sample_50.json --limit 50
  python scripts/run_week2_be1_e2e.py --gold data/annotations/gold.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.service import IngestionService
from app.structuring.service import StructuringService
from scripts.evaluate_structuring import main as evaluate_structuring

DEFAULT_INPUT = PROJECT_ROOT / "data" / "samples" / "week2_delivery_sample_50.json"
DEFAULT_PRED = (
    PROJECT_ROOT / "docs" / "40_delivery" / "week2" / "artifacts" / "be1_structured_pred_50.json"
)
DEFAULT_SUMMARY = (
    PROJECT_ROOT / "docs" / "40_delivery" / "week2" / "artifacts" / "be1_structured_summary_50.json"
)
DEFAULT_EVAL = PROJECT_ROOT / "data" / "annotations" / "week2_structuring_eval_result.json"
RAW_ROOT = PROJECT_ROOT / "data" / "Training" / "01.원천데이터"


def _load_records(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if isinstance(payload, dict):
        if isinstance(payload.get("records"), list):
            return [row for row in payload["records"] if isinstance(row, dict)]
        if isinstance(payload.get("data"), list):
            return [row for row in payload["data"] if isinstance(row, dict)]

    raise ValueError("input JSON must be array or object containing records/data array")


def _collect_raw_samples(limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not RAW_ROOT.exists():
        return rows

    for json_path in sorted(RAW_ROOT.rglob("*.json")):
        if not json_path.is_file():
            continue
        try:
            with json_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue

        if not isinstance(payload, list):
            continue

        for item in payload:
            if not isinstance(item, dict):
                continue

            case_id = str(item.get("case_id") or item.get("id") or "").strip()
            text = str(item.get("text") or "").strip()
            if not case_id or not text:
                continue

            rows.append(
                {
                    "case_id": case_id,
                    "source": "aihub_71852",
                    "created_at": str(item.get("created_at") or item.get("submitted_at") or "").strip(),
                    "category": str(item.get("consulting_category") or item.get("category") or "unknown").strip() or "unknown",
                    "region": str(item.get("region") or "unknown").strip() or "unknown",
                    "raw_text": text,
                    "metadata": {
                        "source_file": str(json_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    },
                }
            )
            if len(rows) >= limit:
                return rows

    return rows


def _as_ingestion_docs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for row in rows:
        docs.append(
            {
                "case_id": row.get("case_id"),
                "source": row.get("source"),
                "created_at": row.get("created_at"),
                "category": row.get("category"),
                "region": row.get("region"),
                "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
                "text": str(row.get("text") or row.get("raw_text") or "").strip(),
                "instructions": row.get("instructions") if isinstance(row.get("instructions"), list) else [],
            }
        )
    return docs


async def _run_pipeline(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ingestion = IngestionService()
    structuring = StructuringService()

    ingest_docs = _as_ingestion_docs(rows)
    processed_docs = await ingestion.process(ingest_docs, clean=True, mask_pii=True)

    structured: List[Dict[str, Any]] = []
    for row in processed_docs:
        structured_row = await structuring.structure(row)
        structured.append(structured_row)

    return structured


def _build_summary(result_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(result_rows)
    if total == 0:
        return {
            "generated_at": datetime.now().isoformat(),
            "total": 0,
            "schema_passed": 0,
            "schema_pass_rate": 0.0,
            "empty_field_rate": 0.0,
        }

    fields = ["observation", "result", "request", "context"]
    schema_passed = 0
    empty_fields = 0

    for row in result_rows:
        validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
        if validation.get("is_valid") is True:
            schema_passed += 1

        for field in fields:
            value = row.get(field)
            text = value.get("text") if isinstance(value, dict) else ""
            if not str(text or "").strip():
                empty_fields += 1

    return {
        "generated_at": datetime.now().isoformat(),
        "total": total,
        "schema_passed": schema_passed,
        "schema_pass_rate": round(schema_passed / total, 4),
        "empty_field_rate": round(empty_fields / (total * len(fields)), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Week2 BE1 E2E pipeline")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSON path")
    parser.add_argument("--pred-output", type=Path, default=DEFAULT_PRED, help="Structured output JSON")
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY, help="Summary output JSON")
    parser.add_argument("--gold", type=Path, default=None, help="Optional gold JSON path for evaluation")
    parser.add_argument("--eval-output", type=Path, default=DEFAULT_EVAL, help="Evaluation output JSON")
    parser.add_argument("--limit", type=int, default=50, help="Max records to process")
    args = parser.parse_args()

    input_path = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    pred_path = args.pred_output if args.pred_output.is_absolute() else PROJECT_ROOT / args.pred_output
    summary_path = args.summary_output if args.summary_output.is_absolute() else PROJECT_ROOT / args.summary_output
    eval_path = args.eval_output if args.eval_output.is_absolute() else PROJECT_ROOT / args.eval_output

    if input_path.exists():
        rows = _load_records(input_path)
    else:
        rows = _collect_raw_samples(args.limit)

    if args.limit > 0 and len(rows) > args.limit:
        rows = rows[: args.limit]

    if not rows:
        raise SystemExit(f"No input records found. input={input_path}")

    structured_rows = asyncio.run(_run_pipeline(rows))

    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pred_path.write_text(json.dumps(structured_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = _build_summary(structured_rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.gold:
        gold_path = args.gold if args.gold.is_absolute() else PROJECT_ROOT / args.gold
        evaluate_structuring(str(gold_path), str(pred_path), str(eval_path))

    print(f"processed={summary['total']} schema_pass_rate={summary['schema_pass_rate']}")
    print(f"pred={pred_path}")
    print(f"summary={summary_path}")
    if args.gold:
        print(f"eval={eval_path}")


if __name__ == "__main__":
    main()

"""정책 Q&A invalid/fallback 건만 재구조화 입력으로 추출한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


DEFAULT_STRUCTURED_PATH = Path("data") / "structured" / "civil_cases_v3_structured_20260619_191733.json"
DEFAULT_SOURCE_INPUT_DIR = Path("data") / "append_inputs" / "civil_cases_v3_policy_qna"
DEFAULT_OUTPUT_DIR = Path("data") / "append_inputs" / "civil_cases_v3_policy_qna_repair_invalid_fallback"


def _load_records(path: Path) -> list[dict[str, Any]]:
    """JSON 루트가 list/object/data 계열이어도 레코드 리스트로 통일한다."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _iter_json_records(input_dir: Path) -> Iterable[dict[str, Any]]:
    """입력 디렉토리 아래 JSON 레코드를 파일명 순서대로 순회한다."""
    for path in sorted(input_dir.rglob("*.json")):
        for record in _load_records(path):
            yield record


def find_repair_case_ids(structured_path: Path) -> set[str]:
    """최종 구조화 결과에서 재처리할 invalid/fallback case_id를 고른다."""
    target_ids: set[str] = set()
    for row in _load_records(structured_path):
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            continue
        validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
        if row.get("structured_by") == "fallback" or validation.get("is_valid") is False:
            target_ids.add(case_id)
    return target_ids


def collect_repair_records(source_input_dir: Path, target_case_ids: set[str]) -> tuple[list[dict[str, Any]], set[str]]:
    """원본 append 입력에서 target case_id에 해당하는 레코드만 원래 순서대로 수집한다."""
    records: list[dict[str, Any]] = []
    found_ids: set[str] = set()
    for record in _iter_json_records(source_input_dir):
        case_id = str(record.get("case_id") or record.get("id") or "").strip()
        if case_id not in target_case_ids or case_id in found_ids:
            continue
        repair_record = dict(record)
        metadata = dict(repair_record.get("metadata") or {})
        metadata["force_policy_qna_repair"] = True
        repair_record["metadata"] = metadata
        repair_record["force_policy_qna_repair"] = True
        records.append(repair_record)
        found_ids.add(case_id)
    return records, target_case_ids - found_ids


def write_chunks(records: list[dict[str, Any]], output_dir: Path, records_per_file: int) -> list[Path]:
    """repair 입력을 build_index.py가 읽는 JSON 배열 파일로 나누어 저장한다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_json = sorted(output_dir.glob("*.json"))
    if existing_json:
        raise FileExistsError(
            f"출력 디렉토리에 기존 JSON 파일이 있습니다. 새 디렉토리를 쓰세요: {output_dir}"
        )

    written: list[Path] = []
    chunk_size = max(1, int(records_per_file))
    for index, start in enumerate(range(0, len(records), chunk_size), start=1):
        output_path = output_dir / f"repair_input_{index:04d}.json"
        chunk = records[start : start + chunk_size]
        output_path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(output_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="정책 Q&A invalid/fallback 재처리 입력 생성")
    parser.add_argument("--structured", type=Path, default=DEFAULT_STRUCTURED_PATH)
    parser.add_argument("--source-input-dir", type=Path, default=DEFAULT_SOURCE_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--records-per-file", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.structured.exists():
        raise FileNotFoundError(f"구조화 결과 파일을 찾을 수 없습니다: {args.structured}")
    if not args.source_input_dir.exists():
        raise FileNotFoundError(f"원본 append 입력 디렉토리를 찾을 수 없습니다: {args.source_input_dir}")

    target_case_ids = find_repair_case_ids(args.structured)
    records, missing_case_ids = collect_repair_records(args.source_input_dir, target_case_ids)
    report = {
        "structured": str(args.structured),
        "source_input_dir": str(args.source_input_dir),
        "output_dir": str(args.output_dir),
        "target_case_count": len(target_case_ids),
        "collected_record_count": len(records),
        "missing_case_count": len(missing_case_ids),
        "missing_case_sample": sorted(missing_case_ids)[:10],
        "records_per_file": args.records_per_file,
        "dry_run": args.dry_run,
    }

    if missing_case_ids:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise RuntimeError("일부 repair 대상 case_id를 원본 append 입력에서 찾지 못했습니다.")

    if not args.dry_run:
        written = write_chunks(records, args.output_dir, args.records_per_file)
        report["written_files"] = [str(path) for path in written]

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

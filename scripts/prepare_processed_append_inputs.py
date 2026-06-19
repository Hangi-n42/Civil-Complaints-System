"""processed 민원 데이터를 append 색인 입력 JSON으로 변환한다.

기존 civil_cases_v3 컬렉션은 case_id가 CASE-{source_id} 형식이다.
`build_index.py`의 AIHub 정규화 경로는 processed 레코드에 대해 source_source_id
형식의 case_id를 만들 수 있으므로, append 색인 전용 입력을 별도로 만든다.

출력 JSON은 `consulting_date`와 `consulting_content`를 의도적으로 제외한다.
그래야 `build_index.py`가 fallback 경로를 사용하고, 여기서 만든 case_id와
search_text를 그대로 유지한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.service import get_ingestion_service


DEFAULT_OUTPUT_DIR = Path("data") / "append_inputs" / "civil_cases_v3_policy_qna"
DEFAULT_CHROMA_SQLITE = Path("data") / "chroma_db" / "chroma.sqlite3"


def _load_records(path: Path) -> list[dict[str, Any]]:
    """JSON 루트가 list/object/data 계열이어도 레코드 리스트로 통일한다."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
        return [payload]
    return []


def _case_id_from_source_id(source_id: str, prefix: str = "") -> str:
    """기존 ID와 충돌하지 않도록 CASE-{prefix}-{source_id} 형식으로 ID를 만든다."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", source_id.strip()).strip("-").upper()
    cleaned_prefix = re.sub(r"[^A-Za-z0-9]+", "-", prefix.strip()).strip("-").upper()
    if not cleaned:
        return ""
    if cleaned_prefix:
        return f"CASE-{cleaned_prefix}-{cleaned}"
    return f"CASE-{cleaned}"


def _normalize_processed_date(value: Any) -> str:
    """processed 날짜를 현재시각 폴백 없이 ISO-8601 KST 문자열로 보존한다."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    kst = timezone(timedelta(hours=9))
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw_value, fmt).replace(tzinfo=kst).isoformat()
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=kst)
        else:
            parsed = parsed.astimezone(kst)
        return parsed.isoformat()
    except ValueError:
        return raw_value


def _read_existing_case_ids(chroma_sqlite: Path, collection_name: str) -> set[str]:
    """Chroma sqlite에서 대상 컬렉션의 기존 case_id 집합을 읽는다."""
    if not chroma_sqlite.exists():
        return set()

    con = sqlite3.connect(str(chroma_sqlite))
    try:
        cur = con.cursor()
        cur.execute("select id from collections where name = ?", (collection_name,))
        row = cur.fetchone()
        if not row:
            return set()

        collection_id = row[0]
        cur.execute("select id from segments where collection = ?", (collection_id,))
        segment_ids = [item[0] for item in cur.fetchall()]
        if not segment_ids:
            return set()

        placeholders = ",".join(["?"] * len(segment_ids))
        cur.execute(
            f"""
            select distinct em.string_value
            from embeddings e
            join embedding_metadata em on em.id = e.id
            where e.segment_id in ({placeholders})
              and em.key = 'case_id'
              and em.string_value is not null
            """,
            tuple(segment_ids),
        )
        return {str(item[0]) for item in cur.fetchall() if item and item[0]}
    finally:
        con.close()


def _iter_input_records(paths: Iterable[Path]) -> Iterable[tuple[Path, dict[str, Any]]]:
    """여러 입력 파일의 레코드를 순서대로 순회한다."""
    for path in paths:
        for record in _load_records(path):
            yield path, record


def _build_append_record(
    raw: dict[str, Any],
    source_file: Path,
    case_id_prefix: str,
    content_type: str = "policy_qna",
    document_type: str = "policy_qna",
) -> dict[str, Any]:
    """processed 레코드를 build_index fallback 입력 스키마로 바꾼다."""
    ingestion = get_ingestion_service()
    normalized = ingestion.normalize_aihub_record(raw, source_file=str(source_file))

    source_id = str(raw.get("source_id") or normalized.get("source_id") or "").strip()
    case_id = _case_id_from_source_id(source_id, prefix=case_id_prefix)
    if not case_id:
        raise ValueError("source_id가 비어 있어 CASE 형식 case_id를 만들 수 없습니다.")

    created_at = (
        _normalize_processed_date(raw.get("consulting_date"))
        or _normalize_processed_date(raw.get("created_at"))
        or _normalize_processed_date(raw.get("submitted_at"))
        or str(normalized.get("created_at") or "")
    )

    clean_content_type = str(content_type or "policy_qna").strip() or "policy_qna"
    clean_document_type = str(document_type or clean_content_type).strip() or clean_content_type

    metadata = dict(normalized.get("metadata") or {})
    metadata.update(
        {
            "source_id": source_id,
            "content_type": clean_content_type,
            "document_type": clean_document_type,
            "adapter": "prepare_processed_append_inputs",
            "input_schema": "processed",
            "source_file": str(source_file),
            "case_id_prefix": case_id_prefix,
            "consulting_date": str(raw.get("consulting_date") or "").strip(),
        }
    )

    # consulting_date/consulting_content/consulting_category는 출력하지 않는다.
    # build_index.py가 normalize_aihub_record를 다시 호출하지 않게 하기 위한 안전장치다.
    return {
        "case_id": case_id,
        "id": case_id,
        "source_id": source_id,
        "content_type": clean_content_type,
        "document_type": clean_document_type,
        "source": normalized.get("source") or raw.get("source") or "unknown",
        "created_at": created_at,
        "submitted_at": created_at,
        "category": normalized.get("category") or raw.get("consulting_category") or "unknown",
        "region": normalized.get("region") or "unknown",
        "raw_text": normalized.get("raw_text") or "",
        "text": normalized.get("text") or normalized.get("raw_text") or "",
        "search_text": normalized.get("search_text") or normalized.get("text") or "",
        "metadata": metadata,
    }


def _write_chunks(records: list[dict[str, Any]], output_dir: Path, records_per_file: int) -> list[Path]:
    """build_index.py가 읽기 쉬운 JSON 배열 파일들로 나누어 저장한다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    chunk_size = max(1, int(records_per_file))

    for index, start in enumerate(range(0, len(records), chunk_size), start=1):
        chunk = records[start : start + chunk_size]
        output_path = output_dir / f"append_input_{index:04d}.json"
        output_path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(output_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="processed JSON을 civil_cases_v3 append 색인 입력으로 변환")
    parser.add_argument(
        "--input",
        action="append",
        type=Path,
        required=True,
        help="processed JSON 경로. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--records-per-file", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체 변환")
    parser.add_argument("--collection-name", default="civil_cases_v3")
    parser.add_argument("--content-type", default="policy_qna", help="색인 문서 유형 메타데이터")
    parser.add_argument("--document-type", default="policy_qna", help="구조화 검증용 문서 유형 메타데이터")
    parser.add_argument(
        "--case-id-prefix",
        default="",
        help="새 데이터 ID namespace. 예: POLICY -> CASE-POLICY-{source_id}",
    )
    parser.add_argument("--chroma-sqlite", type=Path, default=DEFAULT_CHROMA_SQLITE)
    parser.add_argument("--skip-existing", action="store_true", help="대상 컬렉션에 이미 있는 case_id는 출력하지 않음")
    parser.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 통계만 출력")
    args = parser.parse_args()

    missing = [str(path) for path in args.input if not path.exists()]
    if missing:
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {missing}")

    existing_ids = _read_existing_case_ids(args.chroma_sqlite, args.collection_name)
    output_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    duplicate_input_ids: set[str] = set()
    overlap_ids: set[str] = set()
    skipped_existing = 0
    total_seen = 0

    for source_file, raw in _iter_input_records(args.input):
        if args.limit > 0 and total_seen >= args.limit:
            break
        total_seen += 1

        record = _build_append_record(
            raw,
            source_file,
            args.case_id_prefix,
            content_type=args.content_type,
            document_type=args.document_type,
        )
        case_id = str(record.get("case_id") or "")
        if case_id in seen_ids:
            duplicate_input_ids.add(case_id)
            continue
        seen_ids.add(case_id)

        if case_id in existing_ids:
            overlap_ids.add(case_id)
            if args.skip_existing:
                skipped_existing += 1
                continue

        output_records.append(record)

    stats = {
        "input_files": [str(path) for path in args.input],
        "collection_name": args.collection_name,
        "case_id_prefix": args.case_id_prefix,
        "content_type": args.content_type,
        "document_type": args.document_type,
        "existing_case_ids": len(existing_ids),
        "input_seen": total_seen,
        "input_duplicate_case_ids": len(duplicate_input_ids),
        "overlap_with_existing": len(overlap_ids),
        "skipped_existing": skipped_existing,
        "output_records": len(output_records),
        "output_dir": str(args.output_dir),
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    if duplicate_input_ids:
        print("중복 case_id 샘플:", sorted(duplicate_input_ids)[:10])
    if overlap_ids:
        print("기존 컬렉션과 겹치는 case_id 샘플:", sorted(overlap_ids)[:10])

    if args.dry_run:
        return 0

    written = _write_chunks(output_records, args.output_dir, args.records_per_file)
    print(json.dumps({"written_files": [str(path) for path in written]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""ChromaDB에서 특정 case_id 집합의 stale duplicate chunk를 정리한다.

기본은 dry-run이다. repair 재색인처럼 같은 case_id가 다른 chunk_id로 중복 생성된
경우, 기대 chunk_id(case_id__chunk-0)가 이미 존재할 때만 나머지를 삭제한다.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_CHROMA_SQLITE = Path("data") / "chroma_db" / "chroma.sqlite3"
DEFAULT_CHROMA_DIR = Path("data") / "chroma_db"
DEFAULT_REPAIR_INPUT_DIR = Path("data") / "append_inputs" / "civil_cases_v3_policy_qna_repair_invalid_fallback_force"


def _load_records(path: Path) -> list[dict[str, Any]]:
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


def _read_case_ids(input_dir: Path) -> set[str]:
    case_ids: set[str] = set()
    for path in sorted(input_dir.rglob("*.json")):
        for record in _load_records(path):
            case_id = str(record.get("case_id") or record.get("id") or "").strip()
            if case_id:
                case_ids.add(case_id)
    return case_ids


def _get_collection_segments(cur: sqlite3.Cursor, collection_name: str) -> list[str]:
    cur.execute("select id from collections where name=?", (collection_name,))
    row = cur.fetchone()
    if not row:
        return []
    collection_id = row[0]
    cur.execute("pragma table_info(segments)")
    cols = {item[1] for item in cur.fetchall()}
    fk_col = "collection" if "collection" in cols else "collection_id"
    cur.execute(f"select id from segments where {fk_col}=?", (collection_id,))
    return [item[0] for item in cur.fetchall()]


def analyze_duplicates(
    *,
    sqlite_path: Path,
    collection_name: str,
    case_ids: set[str],
) -> dict[str, Any]:
    con = sqlite3.connect(sqlite_path)
    try:
        cur = con.cursor()
        segment_ids = _get_collection_segments(cur, collection_name)
        if not segment_ids:
            raise RuntimeError(f"컬렉션 segment를 찾지 못했습니다: {collection_name}")

        segment_placeholders = ",".join("?" for _ in segment_ids)
        case_placeholders = ",".join("?" for _ in case_ids)
        cur.execute(
            f"""
            select e.id, e.embedding_id, em.string_value as case_id
            from embeddings e
            join embedding_metadata em on em.id=e.id
            where e.segment_id in ({segment_placeholders})
              and em.key='case_id'
              and em.string_value in ({case_placeholders})
            """,
            [*segment_ids, *sorted(case_ids)],
        )
        embedding_rows = cur.fetchall()

        by_internal_id: dict[int, dict[str, str]] = {}
        for internal_id, embedding_id, case_id in embedding_rows:
            by_internal_id[int(internal_id)] = {
                "embedding_id": str(embedding_id),
                "case_id": str(case_id),
                "chunk_id": "",
            }

        if by_internal_id:
            id_placeholders = ",".join("?" for _ in by_internal_id)
            cur.execute(
                f"""
                select id, string_value
                from embedding_metadata
                where id in ({id_placeholders})
                  and key='chunk_id'
                """,
                list(by_internal_id),
            )
            for internal_id, chunk_id in cur.fetchall():
                by_internal_id[int(internal_id)]["chunk_id"] = str(chunk_id or "")

        rows_by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in by_internal_id.values():
            rows_by_case[row["case_id"]].append(row)

        stale_ids: list[str] = []
        missing_current: list[str] = []
        duplicate_distribution = Counter()
        for case_id in sorted(case_ids):
            rows = rows_by_case.get(case_id, [])
            duplicate_distribution[len(rows)] += 1
            expected_chunk_id = f"{case_id}__chunk-0"
            has_current = any(row["chunk_id"] == expected_chunk_id for row in rows)
            if not has_current:
                missing_current.append(case_id)
                continue
            for row in rows:
                if row["chunk_id"] != expected_chunk_id:
                    stale_ids.append(row["embedding_id"])

        return {
            "collection_name": collection_name,
            "target_case_count": len(case_ids),
            "case_count_in_chroma": len(rows_by_case),
            "duplicate_distribution": dict(sorted(duplicate_distribution.items())),
            "current_chunk0_case_count": len(case_ids) - len(missing_current),
            "missing_current_case_count": len(missing_current),
            "missing_current_case_sample": missing_current[:10],
            "stale_id_count": len(stale_ids),
            "stale_id_sample": stale_ids[:10],
            "stale_ids": stale_ids,
        }
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="ChromaDB stale duplicate chunk 정리")
    parser.add_argument("--collection-name", default="civil_cases_v3")
    parser.add_argument("--repair-input-dir", type=Path, default=DEFAULT_REPAIR_INPUT_DIR)
    parser.add_argument("--chroma-sqlite", type=Path, default=DEFAULT_CHROMA_SQLITE)
    parser.add_argument("--chroma-dir", type=Path, default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--apply", action="store_true", help="실제 Chroma delete를 수행")
    args = parser.parse_args()

    case_ids = _read_case_ids(args.repair_input_dir)
    report = analyze_duplicates(
        sqlite_path=args.chroma_sqlite,
        collection_name=args.collection_name,
        case_ids=case_ids,
    )
    report["dry_run"] = not args.apply

    if args.apply:
        if report["missing_current_case_count"] > 0:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            raise RuntimeError("chunk-0 current row가 없는 case가 있어 삭제를 중단합니다. repair 재색인을 먼저 다시 실행하세요.")
        stale_ids = report.pop("stale_ids")
        if stale_ids:
            import chromadb

            client = chromadb.PersistentClient(path=str(args.chroma_dir))
            collection = client.get_collection(args.collection_name)
            collection.delete(ids=stale_ids)
        report["deleted_count"] = len(stale_ids)
    else:
        report.pop("stale_ids", None)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

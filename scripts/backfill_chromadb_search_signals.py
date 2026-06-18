"""ChromaDB 기존 컬렉션에 BE1 검색 신호 metadata를 백필한다.

용도:
  PR #318 이전에 만들어진 `civil_cases_v1` 컬렉션은 `entity_texts`,
  `legal_ref_*`, `key_terms` 같은 metadata가 없다. 전체
  임베딩을 다시 만들지 않고, 저장된 document text와 기존 metadata만 읽어
  deterministic enrichment 신호를 계산한 뒤 metadata만 update한다.

주의:
  - 이 스크립트는 로컬 ChromaDB를 직접 변경한다.
  - `responsible_units`는 실제 BE1 responsible_unit이 없을 때 category/source
    fallback을 사용한다. 담당부서 확정값이 아니라 soft rerank 보조 신호다.
  - `responsible_units_source`는 해당 fallback 출처를 BE2가 구분할 수 있게 보존한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.structuring.enrichment import build_key_terms, normalize_entity_texts
from app.structuring.legal_dictionary import get_legal_ref_matcher
from app.structuring.urgency.scorer import UrgencyScorer

SEARCH_SIGNAL_FIELDS = [
    "entity_texts",
    "legal_ref_names",
    "legal_ref_ids",
    "key_terms",
    "responsible_units",
    "responsible_units_source",
    "urgency_level",
]

_URGENCY_SCORER = UrgencyScorer(model_path="/__missing_urgency_model_for_metadata_backfill__.joblib")


def _split_pipe(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [item for item in value.split("|") if item]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []

    out: list[str] = []
    seen = set()
    for item in raw:
        text = " ".join(str(item or "").split())
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _join_pipe(values: list[Any]) -> str:
    return "|".join(_split_pipe(values))


def _build_signals(text: str, metadata: dict[str, Any]) -> dict[str, str]:
    category = str(metadata.get("category") or "")
    source = str(metadata.get("source") or "")
    entity_texts = normalize_entity_texts([], text)
    legal_refs = get_legal_ref_matcher().match(text)
    key_terms = build_key_terms(text, entity_texts, legal_refs)
    urgency = _URGENCY_SCORER.score(text, category=category)

    responsible_units = []
    for value in (category, source):
        cleaned = " ".join(str(value or "").split())
        if cleaned and cleaned not in {"-", "unknown", "미분류"}:
            responsible_units.append(cleaned)
    responsible_units_value = _join_pipe(responsible_units)

    return {
        "entity_texts": _join_pipe([item.get("text") for item in entity_texts]),
        "legal_ref_names": _join_pipe([item.get("name") for item in legal_refs]),
        "legal_ref_ids": _join_pipe([item.get("law_id") for item in legal_refs]),
        "key_terms": _join_pipe(key_terms),
        "responsible_units": responsible_units_value,
        "responsible_units_source": "category_source_fallback" if responsible_units_value else "",
        "urgency_level": str(urgency.get("level") or ""),
    }


def _coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        field: sum(1 for row in rows if str(row.get(field) or "").strip())
        for field in SEARCH_SIGNAL_FIELDS
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ChromaDB 검색 신호 metadata 백필")
    parser.add_argument("--persist-dir", default=settings.CHROMA_DB_PATH)
    parser.add_argument("--collection", default="civil_cases_v1")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--report",
        default=str(Path("reports") / "retrieval" / "v3" / "chromadb_search_signal_backfill.json"),
    )
    args = parser.parse_args()

    import chromadb

    client = chromadb.PersistentClient(path=str(args.persist_dir))
    collection = client.get_collection(args.collection)
    total = collection.count()
    limit = min(total, args.limit) if args.limit else total
    batch_size = max(1, int(args.batch_size))

    updated = 0
    before_samples: list[dict[str, Any]] = []
    after_samples: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for offset in range(0, limit, batch_size):
        got = collection.get(
            limit=min(batch_size, limit - offset),
            offset=offset,
            include=["documents", "metadatas"],
        )
        ids = got.get("ids") or []
        documents = got.get("documents") or []
        metadatas = got.get("metadatas") or []

        next_metadatas = []
        for storage_id, document, metadata in zip(ids, documents, metadatas):
            current = dict(metadata or {})
            if len(before_samples) < 10:
                before_samples.append({"id": storage_id, "metadata": {k: current.get(k) for k in SEARCH_SIGNAL_FIELDS}})

            signals = _build_signals(str(document or ""), current)
            updated_meta = {**current, **signals}
            next_metadatas.append(updated_meta)
            coverage_rows.append(signals)

            if len(after_samples) < 10:
                after_samples.append({"id": storage_id, "metadata": {k: updated_meta.get(k) for k in SEARCH_SIGNAL_FIELDS}})

        if not args.dry_run and ids:
            collection.update(ids=ids, metadatas=next_metadatas)
        updated += len(ids)
        print(f"[{updated}/{limit}] metadata {'검토' if args.dry_run else '백필'} 완료")

    report = {
        "persist_dir": str(args.persist_dir),
        "collection": args.collection,
        "collection_count": total,
        "processed": updated,
        "dry_run": bool(args.dry_run),
        "coverage": _coverage(coverage_rows),
        "before_samples": before_samples,
        "after_samples": after_samples,
        "responsible_units_note": "category/source fallback; BE1 responsible_unit 확정값 아님",
        "responsible_units_source": "category_source_fallback",
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[report] {report_path}")


if __name__ == "__main__":
    main()

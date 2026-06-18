"""Build a Chroma collection that keeps baseline embeddings and overlays BE1 metadata."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb


OVERLAY_FIELDS = [
    "entity_texts",
    "legal_ref_names",
    "legal_ref_ids",
    "key_terms",
    "responsible_units",
    "responsible_units_source",
    "urgency_level",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist-dir", default="data/chroma_db")
    parser.add_argument("--base-collection", default="civil_cases_v1")
    parser.add_argument("--metadata-collection", default="civil_cases_be1_restructured_v1")
    parser.add_argument("--output-collection", default="civil_cases_v1_be1_metadata_v1")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_build.json"),
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_build.md"),
    )
    return parser.parse_args()


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_value(item) for item in value)
    return bool(value)


def _metadata_key(metadata: dict[str, Any] | None, *, chroma_id: str) -> tuple[str, str]:
    item = metadata or {}
    chunk_id = str(item.get("chunk_id") or "").strip()
    if chunk_id:
        return "chunk_id", chunk_id
    case_id = str(item.get("case_id") or "").strip()
    if case_id:
        return "case_id", case_id
    if "::" in chroma_id:
        return "case_id", chroma_id.split("::", 1)[0]
    if "__chunk-" in chroma_id:
        return "chunk_id", chroma_id.split("::")[-1]
    return "id", chroma_id


def _iter_collection(collection: Any, *, batch_size: int, include: list[str]):
    total = int(collection.count())
    for offset in range(0, total, batch_size):
        yield collection.get(
            limit=min(batch_size, total - offset),
            offset=offset,
            include=include,
        )


def _load_metadata_lookup(collection: Any, *, batch_size: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    duplicate_keys: Counter[str] = Counter()
    total = int(collection.count())

    for batch in _iter_collection(collection, batch_size=batch_size, include=["metadatas"]):
        for chroma_id, metadata in zip(batch.get("ids") or [], batch.get("metadatas") or []):
            item = dict(metadata or {})
            keys = [("id", str(chroma_id))]
            key_type, key_value = _metadata_key(item, chroma_id=str(chroma_id))
            keys.append((key_type, key_value))
            case_id = str(item.get("case_id") or "").strip()
            if case_id:
                keys.append(("case_id", case_id))
            chunk_id = str(item.get("chunk_id") or "").strip()
            if chunk_id:
                keys.append(("chunk_id", chunk_id))

            for prefix, value in keys:
                key = f"{prefix}:{value}"
                if key in lookup:
                    duplicate_keys[key] += 1
                    continue
                lookup[key] = item

    return lookup, {
        "metadata_count": total,
        "lookup_key_count": len(lookup),
        "duplicate_key_count": sum(duplicate_keys.values()),
    }


def _find_source_metadata(
    lookup: dict[str, dict[str, Any]],
    *,
    chroma_id: str,
    base_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    item = base_metadata or {}
    candidates = [f"id:{chroma_id}"]
    chunk_id = str(item.get("chunk_id") or "").strip()
    if chunk_id:
        candidates.append(f"chunk_id:{chunk_id}")
    case_id = str(item.get("case_id") or "").strip()
    if case_id:
        candidates.append(f"case_id:{case_id}")
    key_type, key_value = _metadata_key(item, chroma_id=chroma_id)
    candidates.append(f"{key_type}:{key_value}")

    for key in candidates:
        found = lookup.get(key)
        if found is not None:
            return found
    return None


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    sanitized: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        else:
            sanitized[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return sanitized


def _merge_metadata(
    base: dict[str, Any] | None,
    source: dict[str, Any] | None,
    *,
    base_collection: str,
    metadata_collection: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    merged = dict(base or {})
    decisions: dict[str, str] = {}
    source = source or {}

    for field in OVERLAY_FIELDS:
        source_value = source.get(field)
        base_value = merged.get(field)
        if _has_value(source_value):
            merged[field] = source_value
            decisions[field] = "overlay"
        elif _has_value(base_value):
            decisions[field] = "preserve_base"
        else:
            decisions[field] = "empty"

    merged["metadata_overlay_version"] = "be1_metadata_overlay_v1"
    merged["metadata_overlay_base_collection"] = base_collection
    merged["metadata_overlay_source_collection"] = metadata_collection
    return _sanitize_metadata(merged), decisions


def _count_field_coverage(metadatas: list[dict[str, Any]]) -> dict[str, int]:
    return {
        field: sum(1 for metadata in metadatas if _has_value(metadata.get(field)))
        for field in OVERLAY_FIELDS
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# BE1 Metadata Overlay 컬렉션 구축 결과",
        "",
        f"- 생성 시각(UTC): `{report['generated_at']}`",
        f"- 기준 컬렉션: `{report['base_collection']}`",
        f"- metadata 원본 컬렉션: `{report['metadata_collection']}`",
        f"- 출력 컬렉션: `{report['output_collection']}`",
        f"- 기준 컬렉션 건수: {report['base_count']}",
        f"- 출력 컬렉션 건수: {report['output_count']}",
        f"- metadata 매칭 건수: {report['matched_count']}",
        f"- metadata 미매칭 건수: {report['unmatched_count']}",
        "",
        "## 구축 방식",
        "",
        "- 검색용 document text는 기준 컬렉션 값을 그대로 사용했다.",
        "- 임베딩도 기준 컬렉션 값을 그대로 복사했다.",
        "- BE1 최신 구조화 컬렉션의 검색 신호 metadata만 덮어썼다.",
        "- BE1 값이 비어 있는 필드는 기준 컬렉션의 기존 값을 보존했다.",
        "",
        "## 필드별 최종 적재율",
        "",
        "| 필드 | BE1 값 덮어쓰기 | 기존 값 보존 | 최종 적재 건수 | 최종 적재율 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    decisions = report["overlay_decisions"]
    coverage = report["final_field_coverage"]
    total = max(1, int(report["output_count"]))
    for field in OVERLAY_FIELDS:
        field_decisions = decisions[field]
        count = coverage[field]
        lines.append(
            f"| `{field}` | {field_decisions.get('overlay', 0)} | "
            f"{field_decisions.get('preserve_base', 0)} | {count} / {report['output_count']} | "
            f"{count / total * 100:.2f}% |"
        )

    lines += [
        "",
        "## 해석",
        "",
        "- 이 컬렉션은 검색 본문과 임베딩을 바꾸지 않고 metadata만 보강한 비교 후보이다.",
        "- 검색 성능은 기존 `civil_cases_v1`과 같거나 거의 같아야 한다.",
        "- 성능이 유지되면 이후 soft rerank에서 BE1 metadata를 활용하는 실험으로 넘어갈 수 있다.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    batch_size = max(1, int(args.batch_size))
    client = chromadb.PersistentClient(path=args.persist_dir)

    base_collection = client.get_collection(args.base_collection)
    metadata_collection = client.get_collection(args.metadata_collection)
    metadata_lookup, lookup_stats = _load_metadata_lookup(metadata_collection, batch_size=batch_size)

    if args.replace:
        try:
            client.delete_collection(args.output_collection)
        except Exception:
            pass

    output_collection = client.get_or_create_collection(
        name=args.output_collection,
        metadata={"hnsw:space": "cosine"},
    )

    base_count = int(base_collection.count())
    matched_count = 0
    unmatched_count = 0
    overlay_decisions = {field: Counter() for field in OVERLAY_FIELDS}
    final_metadatas: list[dict[str, Any]] = []

    for batch in _iter_collection(
        base_collection,
        batch_size=batch_size,
        include=["documents", "metadatas", "embeddings"],
    ):
        ids = list(batch.get("ids") or [])
        documents = list(batch.get("documents") or [])
        base_metadatas = list(batch.get("metadatas") or [])
        embeddings = batch.get("embeddings")
        if embeddings is None:
            raise ValueError("base collection did not return embeddings")

        merged_metadatas = []
        for chroma_id, base_metadata in zip(ids, base_metadatas):
            source = _find_source_metadata(
                metadata_lookup,
                chroma_id=str(chroma_id),
                base_metadata=base_metadata,
            )
            if source is None:
                unmatched_count += 1
            else:
                matched_count += 1
            merged, decisions = _merge_metadata(
                base_metadata,
                source,
                base_collection=args.base_collection,
                metadata_collection=args.metadata_collection,
            )
            merged_metadatas.append(merged)
            final_metadatas.append(merged)
            for field, decision in decisions.items():
                overlay_decisions[field][decision] += 1

        output_collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=merged_metadatas,
            embeddings=embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings,
        )
        print(f"[overlay] {min(len(final_metadatas), base_count)}/{base_count}")

    output_count = int(output_collection.count())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "persist_dir": str(args.persist_dir),
        "base_collection": args.base_collection,
        "metadata_collection": args.metadata_collection,
        "output_collection": args.output_collection,
        "base_count": base_count,
        "metadata_count": int(metadata_collection.count()),
        "output_count": output_count,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "lookup": lookup_stats,
        "overlay_fields": OVERLAY_FIELDS,
        "overlay_decisions": {
            field: dict(counter)
            for field, counter in overlay_decisions.items()
        },
        "final_field_coverage": _count_field_coverage(final_metadatas),
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(_render_markdown(report), encoding="utf-8")

    print(f"[done] collection={args.output_collection} count={output_count}")
    print(f"[JSON] {args.out_json}")
    print(f"[Markdown] {args.out_md}")


if __name__ == "__main__":
    main()

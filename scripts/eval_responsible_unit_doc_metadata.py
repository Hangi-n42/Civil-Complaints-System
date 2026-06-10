"""Chroma 문서 metadata의 responsible_units 품질을 평가한다.

query-side 추론 품질이 아니라, 현재 검색 컬렉션에 이미 적재된
문서 metadata가 평가셋 gold와 얼마나 맞는지 확인하는 용도다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_EVAL_FILE = ROOT / "data" / "departments" / "eval" / "responsible_unit_holdout1000.auto.jsonl"
DEFAULT_MASTER_FILE = ROOT / "data" / "departments" / "busan_departments_master.json"
NONE_LABEL = "NONE"


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """JSONL 평가셋을 읽는다."""
    rows: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no} 객체가 아닙니다.")
        rows.append(row)
    return rows


def _load_department_names(path: Path) -> set[str]:
    """마스터에 실제 존재하는 부서명을 읽는다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"마스터 파일 형식이 배열이 아닙니다: {path}")
    return {str(row.get("department", "")).strip() for row in data if row.get("department")}


def _split_units(value: Any) -> List[str]:
    """Chroma metadata의 담당부서 문자열/배열을 top-3 부서 리스트로 정규화한다."""
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value).strip()
        if not text:
            return []
        raw_items = text.replace(",", "|").split("|")

    out: List[str] = []
    for item in raw_items:
        name = str(item or "").strip()
        if name and name not in out:
            out.append(name)
    return out[:3]


def _case_id_from_row(row: Dict[str, Any]) -> str:
    """평가 row에서 Chroma case_id를 만든다."""
    case_id = str(row.get("case_id") or "").strip()
    if case_id:
        return case_id
    source_id = str(row.get("source_id") or "").strip()
    if source_id:
        return source_id if source_id.startswith("CASE-") else f"CASE-{source_id}"
    return ""


def _build_case_metadata_map(
    *,
    persist_dir: str,
    collection: str,
) -> Dict[str, Dict[str, Any]]:
    """Chroma 컬렉션에서 case_id별 대표 metadata를 읽는다.

    같은 case가 여러 chunk로 나뉘어 있으면 chunk_index가 가장 작은 metadata를 사용한다.
    responsible_units metadata는 case 단위로 동일해야 한다는 인덱싱 계약을 전제로 한다.
    """
    import chromadb

    client = chromadb.PersistentClient(path=persist_dir)
    col = client.get_collection(collection)
    payload = col.get(include=["metadatas"])
    case_to_meta: Dict[str, Dict[str, Any]] = {}
    case_to_chunk_index: Dict[str, int] = {}

    for storage_id, metadata in zip(payload.get("ids", []), payload.get("metadatas", [])):
        metadata = metadata or {}
        case_id = str(metadata.get("case_id") or metadata.get("doc_id") or "").strip()
        if not case_id and "::" in str(storage_id):
            case_id = str(storage_id).split("::", 1)[0]
        if not case_id:
            continue
        try:
            chunk_index = int(metadata.get("chunk_index", 0))
        except (TypeError, ValueError):
            chunk_index = 0
        if case_id not in case_to_meta or chunk_index < case_to_chunk_index.get(case_id, 10**9):
            enriched = dict(metadata)
            enriched["_storage_id"] = storage_id
            case_to_meta[case_id] = enriched
            case_to_chunk_index[case_id] = chunk_index
    return case_to_meta


def evaluate_doc_metadata(
    rows: Sequence[Dict[str, Any]],
    *,
    case_metadata: Dict[str, Dict[str, Any]],
    top_k: int = 3,
) -> Dict[str, Any]:
    """평가셋 gold와 Chroma 문서 metadata responsible_units를 비교한다."""
    total = 0
    normal = 0
    none_count = 0
    found = 0
    hit_count = 0
    top1_count = 0
    rr_sum = 0.0
    rank_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    label_source_counts: Counter[str] = Counter()
    by_gold: Dict[str, Counter[str]] = defaultdict(Counter)
    results: List[Dict[str, Any]] = []

    for row in rows:
        gold = [str(value).strip() for value in row.get("gold", []) if str(value).strip()]
        if not gold:
            continue
        total += 1
        case_id = _case_id_from_row(row)
        metadata = case_metadata.get(case_id)
        found_in_chroma = metadata is not None
        found += int(found_in_chroma)
        predictions = _split_units(metadata.get("responsible_units") if metadata else None)[:top_k]
        source = str((metadata or {}).get("responsible_units_source") or "").strip() or "missing"
        label_source = str(row.get("label_source") or "").strip() or "unknown"
        source_counts[source] += 1
        label_source_counts[label_source] += 1

        if gold == [NONE_LABEL]:
            none_count += 1
            hit_rank = 0
            rr = 0.0
        else:
            normal += 1
            hit_rank = 0
            rr = 0.0
            for idx, name in enumerate(predictions, start=1):
                if name in gold:
                    hit_rank = idx
                    rr = 1.0 / idx
                    break
            if hit_rank:
                hit_count += 1
                rr_sum += rr
                rank_counts[f"rank{hit_rank}"] += 1
                if hit_rank == 1:
                    top1_count += 1
            else:
                rank_counts["miss"] += 1
            for name in gold:
                by_gold[name]["total"] += 1
                by_gold[name]["hit"] += int(bool(hit_rank))

        results.append({
            "id": row.get("id", ""),
            "case_id": case_id,
            "source_id": row.get("source_id", ""),
            "gold": gold,
            "predictions": [{"name": name} for name in predictions],
            "hit_rank": hit_rank,
            "found_in_chroma": found_in_chroma,
            "storage_id": (metadata or {}).get("_storage_id", ""),
            "responsible_units_source": source,
            "label_source": label_source,
            "label_confidence": row.get("label_confidence", ""),
            "consulting_category": row.get("original_consulting_category") or row.get("consulting_category", ""),
            "query": row.get("query", ""),
        })

    return {
        "metrics": {
            "eval_target": "doc_metadata",
            "total_cases": total,
            "labeled_cases": normal,
            "none_cases": none_count,
            "found_in_chroma": found,
            "missing_in_chroma": total - found,
            "recall_at_3": round(hit_count / normal, 6) if normal else 0.0,
            "mrr_at_3": round(rr_sum / normal, 6) if normal else 0.0,
            "top1_accuracy": round(top1_count / normal, 6) if normal else 0.0,
            "miss_count": int(rank_counts.get("miss", 0)),
            "rank_counts": dict(rank_counts),
            "responsible_units_source_distribution": dict(source_counts),
            "label_source_distribution": dict(label_source_counts),
        },
        "by_gold": {
            name: {
                "total": counts["total"],
                "hit": counts["hit"],
                "recall_at_3": round(counts["hit"] / counts["total"], 6) if counts["total"] else 0.0,
            }
            for name, counts in sorted(by_gold.items())
        },
        "case_results": results,
    }


def _validate_gold(rows: Sequence[Dict[str, Any]], department_names: set[str]) -> None:
    """평가셋 gold가 마스터 부서명 또는 NONE인지 확인한다."""
    for row in rows:
        for name in row.get("gold", []):
            if name != NONE_LABEL and name not in department_names:
                raise ValueError(f"{row.get('id')} 마스터에 없는 gold 부서: {name}")


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI 인자를 정의한다."""
    parser = argparse.ArgumentParser(description="responsible_units 문서 metadata 평가")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--master-file", type=Path, default=DEFAULT_MASTER_FILE)
    parser.add_argument("--persist-dir", default=str(ROOT / "data" / "chroma_db"))
    parser.add_argument("--collection", default="civil_cases_v1")
    parser.add_argument("--output-json", type=Path, required=True)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI 진입점."""
    args = build_arg_parser().parse_args(argv)
    rows = _load_jsonl(args.eval_file)
    department_names = _load_department_names(args.master_file)
    _validate_gold(rows, department_names)
    case_metadata = _build_case_metadata_map(persist_dir=args.persist_dir, collection=args.collection)
    payload = evaluate_doc_metadata(rows, case_metadata=case_metadata)
    payload["metrics"]["collection"] = args.collection
    payload["metrics"]["persist_dir"] = args.persist_dir
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

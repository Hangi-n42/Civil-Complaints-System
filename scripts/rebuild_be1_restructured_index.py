"""공개 원천데이터로 BE1 재구조화 검색 컬렉션을 만든다.

원천 기준은 `data/Public_Civil_Service_LLM_Data`의 Training/Validation이다.
검색 재색인은 BE1 전처리 계약을 따르며, Q/A 원천 레코드는 민원인 질문과
상담사 답변을 모두 포함한 검색용 본문으로 정규화한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.service import get_ingestion_service
from app.retrieval.service import get_retrieval_service
from app.structuring.enrichment import build_key_terms, normalize_entity_texts
from app.structuring.legal_dictionary import get_legal_ref_matcher
from app.structuring.preprocessing import to_structuring_record
from app.structuring.service import get_structuring_service
from app.structuring.urgency.scorer import UrgencyScorer


DEFAULT_PUBLIC_SOURCE = PROJECT_ROOT / "data" / "Public_Civil_Service_LLM_Data"
DEFAULT_CORPUS_META = PROJECT_ROOT / "data" / "evaluation" / "v3" / "corpus_meta.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "retrieval" / "be1_restructured_records.jsonl"
DEFAULT_FAILURES = PROJECT_ROOT / "logs" / "retrieval" / "be1_restructured_failures.jsonl"

SPEAKER_RE = re.compile(r"(고객|민원인|상담원|상담사|상담자)\s*[:：]\s*")
_URGENCY_SCORER = UrgencyScorer(model_path="/__missing_urgency_model_for_metadata_reindex__.joblib")


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", "\n")).strip()


def _case_id_from_source_id(source_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", source_id.strip()).strip("-").upper()
    return f"CASE-{cleaned}" if cleaned else ""


def _load_corpus_meta(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"corpus must be a list: {path}")
    return [item for item in data if isinstance(item, dict)]


def _load_corpus_order(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for item in _load_corpus_meta(path):
        source_id = str(item.get("source_id") or "").strip()
        if not source_id:
            continue
        out[source_id] = {
            "case_id": str(item.get("case_id") or "").strip(),
            "chunk_id": str(item.get("chunk_id") or "").strip(),
        }
    return out


def _read_json_records(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _source_json_files(source_dir: Path) -> List[Path]:
    files: List[Path] = []
    for path in source_dir.rglob("*.json"):
        if "01.원천데이터" not in path.parts:
            continue
        files.append(path)
    return sorted(files, key=lambda item: str(item))


def _parse_title_q(content: str) -> Dict[str, str] | None:
    title_match = re.search(
        r"(?:^|\n)\s*[\"'“”]?\s*제목\s*[:：]\s*(.*?)(?=(?:^|\n)\s*[\"'“”]?\s*Q\s*[:：]|\Z)",
        content,
        flags=re.DOTALL,
    )
    q_match = re.search(
        r"(?:^|\n)\s*[\"'“”]?\s*Q\s*[:：]\s*(.*?)(?=(?:^|\n)\s*[\"'“”]?\s*A\s*[:：]|\Z)",
        content,
        flags=re.DOTALL,
    )
    if not title_match and not q_match:
        return None

    title = _clean_text(title_match.group(1)) if title_match else ""
    question = _clean_text(q_match.group(1)) if q_match else ""
    return {"title": title, "client_question": question}


def _extract_customer_turns(content: str) -> str:
    matches = list(SPEAKER_RE.finditer(content))
    if not matches:
        return ""

    turns: List[str] = []
    for idx, match in enumerate(matches):
        speaker = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        if speaker in {"고객", "민원인"}:
            text = _clean_text(content[start:end])
            if text:
                turns.append(text)
    return "\n".join(turns)


def _extract_civil_source_text(raw_record: Dict[str, Any], normalized: Dict[str, Any]) -> tuple[str, str]:
    # 검색 재색인 본문은 운영 전처리 어댑터의 답변 포함 텍스트를 우선한다.
    search_text = _clean_text(normalized.get("search_text"))
    if search_text:
        return search_text, "search_text_with_answer"

    normalized_text = _clean_text(normalized.get("raw_text") or normalized.get("text"))
    if normalized_text:
        return normalized_text, "structuring_text_fallback"

    prepared_text = _clean_text(to_structuring_record(raw_record).get("text"))
    if prepared_text:
        return prepared_text, "adapter_search_text"

    content = str(raw_record.get("consulting_content") or "").strip()
    content = content.strip("\"'“”")
    qa_parts = _parse_title_q(content)
    if qa_parts:
        return _clean_text("\n".join(part for part in (qa_parts.get("title"), qa_parts.get("client_question")) if part)), "title_q_fallback"

    dialogue_text = _extract_customer_turns(content)
    if dialogue_text:
        return dialogue_text, "customer_turns_fallback"

    return _clean_text(content), "fallback_full_content"


def _build_public_source_record(
    raw_record: Dict[str, Any],
    *,
    source_file: Path,
    corpus_order: Dict[str, Dict[str, str]],
    ingestion: Any,
) -> Dict[str, Any]:
    normalized = ingestion.normalize_aihub_record(raw_record, source_file=str(source_file))
    text, parse_mode = _extract_civil_source_text(raw_record, normalized)

    source_id = str(raw_record.get("source_id") or normalized.get("source_id") or "").strip()
    ordered = corpus_order.get(source_id, {})
    case_id = ordered.get("case_id") or _case_id_from_source_id(source_id)
    if not case_id:
        case_id = str(normalized.get("case_id") or "").strip()
    chunk_id = ordered.get("chunk_id") or f"{case_id}__chunk-0"

    category = str(normalized.get("category") or "unknown").strip() or "unknown"
    if category == "-":
        category = "unknown"

    return {
        "case_id": case_id,
        "id": case_id,
        "doc_id": case_id,
        "chunk_id": chunk_id,
        "source_id": source_id,
        "source": str(normalized.get("source") or raw_record.get("source") or "unknown"),
        "category": category,
        "region": str(normalized.get("region") or ""),
        "created_at": normalized.get("created_at"),
        "text": text,
        "raw_text": text,
        "metadata": {
            "source_id": source_id,
            "source_file": str(source_file),
            "source_type": str((normalized.get("metadata") or {}).get("source_type") or ""),
            "parse_mode": parse_mode,
            "input_mode": "public_source",
            "consulting_turns": (normalized.get("metadata") or {}).get("consulting_turns"),
            "consulting_length": (normalized.get("metadata") or {}).get("consulting_length"),
        },
    }


def _load_public_source_records(source_dir: Path, corpus_meta: Path) -> List[Dict[str, Any]]:
    ingestion = get_ingestion_service()
    corpus_order = _load_corpus_order(corpus_meta)
    by_source_id: Dict[str, Dict[str, Any]] = {}
    without_source_id: List[Dict[str, Any]] = []

    for path in _source_json_files(source_dir):
        for raw_record in _read_json_records(path):
            record = _build_public_source_record(
                raw_record,
                source_file=path,
                corpus_order=corpus_order,
                ingestion=ingestion,
            )
            source_id = record["source_id"]
            if source_id:
                by_source_id[source_id] = record
            else:
                without_source_id.append(record)

    ordered_records: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for source_id in corpus_order:
        record = by_source_id.get(source_id)
        if record:
            ordered_records.append(record)
            seen.add(source_id)

    extras = [record for sid, record in by_source_id.items() if sid not in seen]
    extras.sort(key=lambda item: (item.get("source") or "", item.get("source_id") or ""))
    without_source_id.sort(key=lambda item: (item.get("source") or "", item.get("case_id") or ""))
    return ordered_records + extras + without_source_id


def _load_corpus_meta_records(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for item in _load_corpus_meta(path):
        chunk_text = str(item.get("chunk_text") or "").strip()
        records.append(
            {
                "case_id": str(item.get("case_id") or "").strip(),
                "id": str(item.get("case_id") or "").strip(),
                "doc_id": str(item.get("case_id") or "").strip(),
                "chunk_id": str(item.get("chunk_id") or "").strip(),
                "source_id": str(item.get("source_id") or "").strip(),
                "source": str(item.get("source") or ""),
                "category": str(item.get("category") or "unknown"),
                "region": str(item.get("source") or ""),
                "created_at": item.get("created_at"),
                "text": chunk_text,
                "raw_text": chunk_text,
                "metadata": {
                    "source_id": str(item.get("source_id") or ""),
                    "input_mode": "corpus_meta",
                },
            }
        )
    return records


def _load_done_ids(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            case_id = str(item.get("case_id") or "").strip()
            if case_id:
                done.add(case_id)
    return done


def _append_jsonl(path: Path, item: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def _split_structured_text(structured: Dict[str, Any], fallback_text: str) -> Dict[str, str]:
    parts: Dict[str, str] = {}
    for key in ("observation", "result", "request", "context"):
        value = structured.get(key)
        if isinstance(value, dict):
            text = str(value.get("text") or value.get("request") or "").strip()
            if text and text not in {"없음", "해당없음", "-", "N/A"}:
                parts[key] = text
    if not parts:
        parts["observation"] = fallback_text
    return parts


def _field(structured: Dict[str, Any], key: str, text: str) -> Dict[str, Any]:
    raw = structured.get(key)
    out: Dict[str, Any] = {"text": text}
    if isinstance(raw, dict) and "confidence" in raw:
        out["confidence"] = raw.get("confidence")
    return out


def _fallback_responsible_units(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for value in (record.get("category"), record.get("source")):
        name = " ".join(str(value or "").split())
        if not name or name in {"-", "unknown", "미분류"} or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        units.append(
            {
                "name": name,
                "confidence": 0.0,
                "evidence": [],
                "source": "category_source_fallback",
            }
        )
    return units


def _build_deterministic_structured(record: Dict[str, Any]) -> Dict[str, Any]:
    text = str(record.get("text") or record.get("raw_text") or "").strip()
    category = str(record.get("category") or "unknown")
    entity_texts = normalize_entity_texts([], text)
    legal_refs = get_legal_ref_matcher().match(text)
    key_terms = build_key_terms(text, entity_texts, legal_refs)

    return {
        "case_id": record.get("case_id"),
        "source": record.get("source"),
        "created_at": record.get("created_at"),
        "category": category,
        "region": record.get("region"),
        "raw_text": text,
        "observation": {"text": text, "confidence": 1.0},
        "entities": [],
        "entity_texts": entity_texts,
        "legal_refs": legal_refs,
        "key_terms": key_terms,
        "responsible_unit": _fallback_responsible_units(record),
        "urgency": _URGENCY_SCORER.score(text, category=category),
        "structured_by": "deterministic_search_signals",
        "confidence_score": 0.0,
        "validation": {"is_valid": True},
    }


def _build_index_record(input_item: Dict[str, Any], structured: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(input_item.get("case_id") or structured.get("case_id") or "").strip()
    chunk_id = str(input_item.get("chunk_id") or f"{case_id}__chunk-0").strip()
    chunk_text = str(input_item.get("text") or input_item.get("raw_text") or "").strip()
    metadata = input_item.get("metadata") if isinstance(input_item.get("metadata"), dict) else {}
    structured_text = _split_structured_text(structured, chunk_text)
    combined_text = "\n".join(structured_text[key] for key in ("observation", "result", "request", "context") if key in structured_text)

    record: Dict[str, Any] = {
        "case_id": case_id,
        "id": case_id,
        "doc_id": case_id,
        "chunk_id": chunk_id,
        "source": str(input_item.get("source") or structured.get("source") or "unknown"),
        "category": str(input_item.get("category") or structured.get("category") or "unknown"),
        "region": str(input_item.get("region") or structured.get("region") or ""),
        "created_at": structured.get("created_at"),
        "text": combined_text,
        "raw_text": chunk_text,
        "structured_text": structured_text,
        "entities": structured.get("entities") or [],
        "entity_texts": structured.get("entity_texts") or [],
        "legal_refs": structured.get("legal_refs") or [],
        "key_terms": structured.get("key_terms") or [],
        "responsible_unit": structured.get("responsible_unit") or [],
        "urgency": structured.get("urgency") or {},
        "metadata": {
            "source_id": str(input_item.get("source_id") or metadata.get("source_id") or ""),
            "source": str(input_item.get("source") or structured.get("source") or "unknown"),
            "category": str(input_item.get("category") or structured.get("category") or "unknown"),
            "region": str(input_item.get("region") or structured.get("region") or ""),
            "source_type": str(metadata.get("source_type") or ""),
            "parse_mode": str(metadata.get("parse_mode") or ""),
            "input_mode": str(metadata.get("input_mode") or ""),
            "structured_by": structured.get("structured_by", "fallback"),
            "structuring_confidence": structured.get("confidence_score", 0.0),
            "is_valid": (structured.get("validation") or {}).get("is_valid", False),
            "pipeline_version": "be1_restructured_v1",
            "content_type": "be1_restructured",
        },
    }
    for key, text in structured_text.items():
        record[key] = _field(structured, key, text)
    return record


async def _index_batch(
    *,
    records: List[Dict[str, Any]],
    collection_name: str,
    rebuild: bool,
) -> Dict[str, Any]:
    service = get_retrieval_service()
    return await service.index_documents(records, rebuild=rebuild, collection_name=collection_name)


async def main() -> None:
    parser = argparse.ArgumentParser(description="BE1 전체 재구조화 컬렉션 빌드")
    parser.add_argument(
        "--input-mode",
        choices=("public-source", "corpus-meta"),
        default="public-source",
        help="public-source: 원천 Training+Validation, corpus-meta: 현재 V3 corpus_meta",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_PUBLIC_SOURCE)
    parser.add_argument("--corpus-meta", type=Path, default=DEFAULT_CORPUS_META)
    parser.add_argument("--collection-name", default="civil_cases_be1_restructured_v1")
    parser.add_argument(
        "--structuring-mode",
        choices=("actual", "deterministic-signals"),
        default="actual",
        help="actual: BE1 LLM 구조화 실행, deterministic-signals: 최신 검색 신호만 계산",
    )
    parser.add_argument("--output-jsonl", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--failures-jsonl", type=Path, default=DEFAULT_FAILURES)
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-index", action="store_true", help="구조화 산출물만 저장하고 Chroma에는 적재하지 않음")
    parser.add_argument("--no-rebuild", action="store_true", help="첫 인덱싱 배치에서 컬렉션 초기화를 하지 않음")
    args = parser.parse_args()

    if args.input_mode == "public-source":
        corpus = _load_public_source_records(args.input, args.corpus_meta)
    else:
        corpus = _load_corpus_meta_records(args.corpus_meta if args.input == DEFAULT_PUBLIC_SOURCE else args.input)

    if args.limit > 0:
        corpus = corpus[: args.limit]

    done_ids = _load_done_ids(args.output_jsonl) if args.resume else set()
    if not args.resume:
        args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.output_jsonl.write_text("", encoding="utf-8")
        args.failures_jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.failures_jsonl.write_text("", encoding="utf-8")

    structuring = get_structuring_service()
    ingestion = get_ingestion_service()
    batch: List[Dict[str, Any]] = []
    indexed_batches = 0
    processed = 0
    skipped = 0
    failed = 0
    started = time.time()

    for idx, item in enumerate(corpus, start=1):
        case_id = str(item.get("case_id") or "").strip()
        if case_id in done_ids:
            skipped += 1
            continue

        try:
            text = str(item.get("text") or item.get("raw_text") or "").strip()
            text = await ingestion.clean_text(text)
            text = await ingestion.mask_pii(text)
            if not text:
                raise ValueError("empty civil text")

            record = {
                "case_id": case_id,
                "source_id": str(item.get("source_id") or ""),
                "source": str(item.get("source") or ""),
                "created_at": item.get("created_at"),
                "category": str(item.get("category") or "unknown"),
                "region": str(item.get("region") or ""),
                "text": text,
                "raw_text": text,
                "metadata": {
                    **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                    "chunk_id": str(item.get("chunk_id") or ""),
                },
            }
            item["text"] = text
            item["raw_text"] = text
            if args.structuring_mode == "deterministic-signals":
                structured = _build_deterministic_structured(record)
            else:
                structured = await structuring.structure(record)
            index_record = _build_index_record(item, structured)
            _append_jsonl(args.output_jsonl, index_record)
            batch.append(index_record)
            processed += 1
        except Exception as exc:
            failed += 1
            _append_jsonl(
                args.failures_jsonl,
                {
                    "case_id": case_id,
                    "chunk_id": item.get("chunk_id"),
                    "source_id": item.get("source_id"),
                    "error": str(exc),
                },
            )

        should_flush = len(batch) >= max(1, args.batch_size)
        is_last = idx == len(corpus)
        if batch and not args.no_index and (should_flush or is_last):
            rebuild = indexed_batches == 0 and not args.no_rebuild and not args.resume
            result = await _index_batch(
                records=batch,
                collection_name=args.collection_name,
                rebuild=rebuild,
            )
            indexed_batches += 1
            print(
                f"[index] batch={indexed_batches} rebuild={rebuild} "
                f"indexed={result.get('indexed_count')} collection={args.collection_name}"
            )
            batch.clear()

        progress_every = max(1, int(args.progress_every))
        if idx == len(corpus) or idx % progress_every == 0 or should_flush:
            elapsed = time.time() - started
            print(
                f"[progress] seen={idx}/{len(corpus)} processed={processed} "
                f"skipped={skipped} failed={failed} elapsed_sec={elapsed:.1f}"
            )

    print(
        json.dumps(
            {
                "input_mode": args.input_mode,
                "input": str(args.input),
                "corpus_meta": str(args.corpus_meta),
                "collection_name": args.collection_name,
                "structuring_mode": args.structuring_mode,
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "output_jsonl": str(args.output_jsonl),
                "failures_jsonl": str(args.failures_jsonl),
                "elapsed_sec": round(time.time() - started, 2),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

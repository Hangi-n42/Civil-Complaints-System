"""AI Hub 원천 데이터 또는 legacy evaluation_set을 BEIR 호환 검색 평가셋으로 변환한다."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.structuring.service import StructuringService
from app.structuring.preprocessing import to_structuring_record


@dataclass(frozen=True)
class CorpusRow:
    _id: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryRow:
    _id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QrelRow:
    qid: str
    docid: str
    relevance: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="검색 평가셋 v1 생성기(BEIR 호환)")
    parser.add_argument("--source", type=str, default="", help="legacy evaluation_set.json 경로")
    parser.add_argument("--source-dir", type=str, default="", help="AI Hub 원천 JSON 디렉터리 경로")
    parser.add_argument("--output-dir", type=str, default="data/eval/retrieval/v1")
    parser.add_argument("--smoke-size", type=int, default=50, help="smoke subset query 수")
    parser.add_argument("--max-files", type=int, default=0, help="source-dir 사용 시 최대 파일 수(0=전체)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    smoke_size = max(1, int(args.smoke_size))
    max_files = max(0, int(args.max_files))

    if args.source_dir:
        source_root = Path(args.source_dir)
        corpus, queries, qrels, source_stats = convert_aihub_source_dir(source_root, max_files=max_files)
        source_descriptor = {
            "source_mode": "aihub_source_dir",
            "source_dir": str(source_root),
            "scanned_files": source_stats["scanned_files"],
            "used_files": source_stats["used_files"],
        }
        source_hash = ""
    elif args.source:
        source_path = Path(args.source)
        with source_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise SystemExit("source 파일은 list 형식의 evaluation_set 이어야 합니다.")
        corpus, queries, qrels = convert_legacy_eval_set(payload)
        source_descriptor = {
            "source_mode": "legacy_evaluation_set",
            "source_file": str(source_path),
        }
        source_hash = _sha256_file(source_path)
    else:
        raise SystemExit("--source 또는 --source-dir 중 하나는 반드시 지정해야 합니다.")

    if not queries:
        raise SystemExit("변환 가능한 query가 없습니다.")
    if not qrels:
        raise SystemExit("qrels가 비어 있습니다. source 형식을 확인하세요.")

    write_eval_set(output_dir, corpus, queries, qrels)
    write_smoke_subset(output_dir / "smoke", queries, qrels, smoke_size=smoke_size)
    write_manifest(
        output_dir,
        source_descriptor=source_descriptor,
        source_hash=source_hash,
        corpus=corpus,
        queries=queries,
        qrels=qrels,
        smoke_size=smoke_size,
    )
    return 0


def convert_legacy_eval_set(
    cases: list[dict[str, Any]],
) -> tuple[list[CorpusRow], list[QueryRow], list[QrelRow]]:
    corpus_by_id: dict[str, CorpusRow] = {}
    queries: list[QueryRow] = []
    qrels: list[QrelRow] = []

    for case in cases:
        if not isinstance(case, dict):
            continue
        qid = str(case.get("case_id") or case.get("qid") or "").strip()
        query_text = str(case.get("query") or "").strip()
        if not qid or not query_text:
            continue

        metadata = {
            "scenario_type": str(case.get("scenario_type") or "unknown").lower(),
            "risk_level": str(case.get("risk_level") or "unknown").lower(),
            "topic_type": str(case.get("topic_type") or case.get("category") or "general").lower(),
            "complexity_level": str(case.get("complexity_level") or "medium").lower(),
            "source_case_id": qid,
        }
        queries.append(QueryRow(_id=qid, text=query_text, metadata=metadata))

        for ctx in case.get("context") or []:
            if not isinstance(ctx, dict):
                continue
            docid = str(ctx.get("chunk_id") or ctx.get("doc_id") or "").strip()
            if not docid:
                continue

            if docid not in corpus_by_id:
                corpus_by_id[docid] = CorpusRow(
                    _id=docid,
                    title=str(ctx.get("title") or f"{qid} 컨텍스트"),
                    text=str(ctx.get("chunk_text") or ctx.get("text") or "").strip(),
                    metadata={
                        "case_id": str(ctx.get("case_id") or qid),
                        "category": str(ctx.get("category") or metadata["topic_type"]),
                        "region": str(ctx.get("region") or "unknown"),
                        "source": str(ctx.get("source") or "legacy_eval_set"),
                    },
                )

            relevance = int(ctx.get("relevance") or _fallback_relevance(ctx))
            qrels.append(QrelRow(qid=qid, docid=docid, relevance=max(0, min(3, relevance))))

    unique_qrels = sorted(
        {(row.qid, row.docid): row for row in qrels}.values(),
        key=lambda row: (row.qid, row.docid),
    )
    return sorted(corpus_by_id.values(), key=lambda row: row._id), queries, unique_qrels


def convert_aihub_source_dir(
    source_dir: Path,
    *,
    max_files: int,
) -> tuple[list[CorpusRow], list[QueryRow], list[QrelRow], dict[str, int]]:
    if not source_dir.exists():
        raise SystemExit(f"source-dir 경로가 존재하지 않습니다: {source_dir}")

    files = sorted(source_dir.rglob("*.json"))
    if max_files > 0:
        files = files[:max_files]

    corpus: list[CorpusRow] = []
    queries: list[QueryRow] = []
    qrels: list[QrelRow] = []
    seen_docids: set[str] = set()
    scanned_files = 0
    used_files = 0
    doc_records: dict[str, dict[str, Any]] = {}
    pending_queries: list[tuple[QueryRow, str]] = []
    structuring_service = StructuringService()
    structuring_service.logger.disabled = True

    for path in files:
        scanned_files += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, list):
            continue
        rows = [row for row in payload if isinstance(row, dict)]
        if not rows:
            continue

        local_has_query = False
        for row in rows:
            source_id = str(row.get("source_id") or path.stem).strip() or path.stem
            docid = f"{source_id}__chunk-0"
            raw_text = str(to_structuring_record(row).get("text") or "").strip()
            if docid not in seen_docids:
                seen_docids.add(docid)
                category = str(row.get("consulting_category") or "")
                text = raw_text
                corpus_row = CorpusRow(
                    _id=docid,
                    title=category or source_id,
                    text=text,
                    metadata={
                        "source_id": source_id,
                        "source": str(row.get("source") or "aihub"),
                        "consulting_date": str(row.get("consulting_date") or ""),
                        "consulting_category": category,
                        "topic_type": _normalize_topic(category),
                    },
                )
                corpus.append(corpus_row)
                doc_records[docid] = {
                    "source_id": source_id,
                    "topic_type": corpus_row.metadata["topic_type"],
                    "category": category,
                    "text_tokens": _tokenize(text),
                }

            query_row = _build_four_element_query_row(
                row=row,
                source_id=source_id,
                docid=docid,
                raw_text=raw_text,
                service=structuring_service,
            )
            if query_row is not None:
                queries.append(query_row)
                pending_queries.append((query_row, docid))
                local_has_query = True

        if local_has_query:
            used_files += 1

    qrels = _build_similar_case_qrels(pending_queries, doc_records)
    valid_qids = {row.qid for row in qrels}
    queries = [row for row in queries if row._id in valid_qids]

    unique_qrels = sorted(
        {(row.qid, row.docid): row for row in qrels}.values(),
        key=lambda row: (row.qid, row.docid),
    )
    return corpus, queries, unique_qrels, {"scanned_files": scanned_files, "used_files": used_files}


def write_eval_set(
    output_dir: Path,
    corpus: list[CorpusRow],
    queries: list[QueryRow],
    qrels: list[QrelRow],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "corpus.jsonl", (asdict(row) for row in corpus))
    _write_jsonl(output_dir / "queries.jsonl", (asdict(row) for row in queries))
    with (output_dir / "qrels.tsv").open("w", encoding="utf-8") as handle:
        handle.write("qid\tdocid\trelevance\n")
        for row in qrels:
            handle.write(f"{row.qid}\t{row.docid}\t{row.relevance}\n")


def write_smoke_subset(output_dir: Path, queries: list[QueryRow], qrels: list[QrelRow], smoke_size: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_queries = queries[: min(smoke_size, len(queries))]
    selected_qids = {row._id for row in selected_queries}
    selected_qrels = [row for row in qrels if row.qid in selected_qids]
    _write_jsonl(output_dir / "queries.jsonl", (asdict(row) for row in selected_queries))
    with (output_dir / "qrels.tsv").open("w", encoding="utf-8") as handle:
        handle.write("qid\tdocid\trelevance\n")
        for row in selected_qrels:
            handle.write(f"{row.qid}\t{row.docid}\t{row.relevance}\n")


def write_manifest(
    output_dir: Path,
    *,
    source_descriptor: dict[str, Any],
    source_hash: str,
    corpus: list[CorpusRow],
    queries: list[QueryRow],
    qrels: list[QrelRow],
    smoke_size: int,
) -> None:
    manifest = {
        "dataset_version": "v1",
        **source_descriptor,
        "source_file_sha256": source_hash,
        "counts": {
            "corpus": len(corpus),
            "queries": len(queries),
            "qrels": len(qrels),
            "smoke_size": min(smoke_size, len(queries)),
        },
        "files": {
            "corpus_jsonl_sha256": _sha256_file(output_dir / "corpus.jsonl"),
            "queries_jsonl_sha256": _sha256_file(output_dir / "queries.jsonl"),
            "qrels_tsv_sha256": _sha256_file(output_dir / "qrels.tsv"),
        },
        "qrels_guideline": {
            "3": "질문에 직접 답할 수 있는 핵심 근거",
            "2": "답변에 중요하지만 단독으로는 부족한 근거",
            "1": "주제 또는 절차상 약하게 관련",
            "0": "무관 또는 오답 유도 가능",
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_four_element_query_row(
    *,
    row: dict[str, Any],
    source_id: str,
    docid: str,
    raw_text: str,
    service: StructuringService,
) -> QueryRow | None:
    if not raw_text:
        return None

    structured = asyncio.run(service.structure(raw_text))
    observation = _clean_field_text(str((structured.get("observation") or {}).get("text") or ""))
    result = _clean_field_text(str((structured.get("result") or {}).get("text") or ""))
    request = _clean_field_text(str((structured.get("request") or {}).get("text") or ""))
    context = _clean_field_text(str((structured.get("context") or {}).get("text") or ""))
    entities = structured.get("entities") or []

    if not any([observation, result, request, context]):
        fallback = _fallback_query_from_content(raw_text)
        if not fallback:
            return None
        observation = fallback

    query_text = _format_four_element_query(observation, result, request, context)
    entity_labels = sorted({str(item.get("label") or "").strip().upper() for item in entities if isinstance(item, dict)})

    return QueryRow(
        _id=f"{source_id}__case-0",
        text=query_text,
        metadata={
            "scenario_type": "unknown",
            "risk_level": "unknown",
            "topic_type": _normalize_topic(row.get("consulting_category")),
            "complexity_level": _complexity_from_text(query_text),
            "source_case_id": source_id,
            "query_observation": observation,
            "query_result": result,
            "query_request": request,
            "query_context": context,
            "query_entity_labels": entity_labels,
            "query_docid": docid,
        },
    )


def _fallback_query_from_content(content: str) -> str:
    if not content:
        return ""
    first_line = content.splitlines()[0].strip()
    return first_line[:200]


def _clean_field_text(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    greetings = (
        "안녕하십니까",
        "무엇을 도와드릴까요",
        "여보세요",
        "감사합니다",
    )
    for token in greetings:
        text = text.replace(token, "").strip()
    text = re.sub(r"^[고객상담원민원인답변자:\-\s]+", "", text).strip()
    if len(text) < 6:
        return ""
    return text


def _format_four_element_query(observation: str, result: str, request: str, context: str) -> str:
    sections = []
    if observation:
        sections.append(f"관찰: {observation}")
    if result:
        sections.append(f"결과: {result}")
    if request:
        sections.append(f"요청: {request}")
    if context:
        sections.append(f"맥락: {context}")
    return "\n".join(sections)


def _normalize_topic(raw_category: Any) -> str:
    value = str(raw_category or "").strip().lower()
    if not value:
        return "general"
    if "교통" in value or "도로" in value:
        return "traffic"
    if "복지" in value or "지원" in value:
        return "welfare"
    if "환경" in value or "악취" in value or "소음" in value:
        return "environment"
    return "general"


def _complexity_from_instruction(item: dict[str, Any]) -> str:
    input_length = str(item.get("input_length") or "").strip()
    if input_length.isdigit():
        length = int(input_length)
        if length >= 900:
            return "high"
        if length >= 300:
            return "medium"
        return "low"
    return "medium"


def _complexity_from_text(text: str) -> str:
    length = len(str(text or ""))
    if length >= 500:
        return "high"
    if length >= 180:
        return "medium"
    return "low"


def _build_similar_case_qrels(
    pending_queries: list[tuple[QueryRow, str]],
    doc_records: dict[str, dict[str, Any]],
) -> list[QrelRow]:
    qrels: list[QrelRow] = []
    by_topic: dict[str, list[str]] = {}
    for docid, info in doc_records.items():
        topic = str(info.get("topic_type") or "general")
        by_topic.setdefault(topic, []).append(docid)

    for query_row, origin_docid in pending_queries:
        query_tokens = _tokenize(query_row.text)
        if not query_tokens:
            continue
        topic = str(query_row.metadata.get("topic_type") or "general")
        candidate_ids = by_topic.get(topic, [])
        scored: list[tuple[str, float]] = []
        for docid in candidate_ids:
            if docid == origin_docid:
                continue
            tokens = doc_records[docid]["text_tokens"]
            score = _jaccard(query_tokens, tokens)
            if score <= 0:
                continue
            scored.append((docid, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        if not scored:
            continue
        top_candidates = scored[:3]
        for docid, score in top_candidates:
            qrels.append(QrelRow(qid=query_row._id, docid=docid, relevance=_score_to_relevance(score)))
    return qrels


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9가-힣_]+", str(text or "").lower())
    return {token for token in tokens if len(token) >= 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _score_to_relevance(score: float) -> int:
    if score >= 0.18:
        return 3
    if score >= 0.1:
        return 2
    return 1


def _fallback_relevance(ctx: dict[str, Any]) -> int:
    score = ctx.get("score")
    if isinstance(score, (int, float)):
        if float(score) >= 0.85:
            return 3
        if float(score) >= 0.6:
            return 2
        return 1
    return 1


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())

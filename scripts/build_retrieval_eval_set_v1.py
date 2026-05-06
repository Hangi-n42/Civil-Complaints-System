"""AI Hub legacy evaluation_set을 BEIR 호환 검색 평가셋으로 변환한다."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


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
    parser.add_argument("--source", type=str, required=True, help="legacy evaluation_set.json 경로")
    parser.add_argument("--output-dir", type=str, default="data/eval/retrieval/v1")
    parser.add_argument("--smoke-size", type=int, default=50, help="smoke subset query 수")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.source)
    output_dir = Path(args.output_dir)
    smoke_size = max(1, int(args.smoke_size))

    with source_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise SystemExit("source 파일은 list 형식의 evaluation_set 이어야 합니다.")

    corpus, queries, qrels = convert_legacy_eval_set(payload)
    if not queries:
        raise SystemExit("변환 가능한 query가 없습니다.")
    if not qrels:
        raise SystemExit("qrels가 비어 있습니다. source 형식을 확인하세요.")

    write_eval_set(output_dir, corpus, queries, qrels)
    write_smoke_subset(output_dir / "smoke", queries, qrels, smoke_size=smoke_size)
    write_manifest(output_dir, source_path, corpus, queries, qrels, smoke_size=smoke_size)
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
    source_path: Path,
    corpus: list[CorpusRow],
    queries: list[QueryRow],
    qrels: list[QrelRow],
    smoke_size: int,
) -> None:
    manifest = {
        "dataset_version": "v1",
        "source_file": str(source_path),
        "source_file_sha256": _sha256_file(source_path),
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


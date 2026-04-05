"""Issue #101-3 runner: BGE-m3 embedding + ChromaDB indexing for evaluation_set.

Usage:
  c:/Projects/AI-Civil-Affairs-Systems/.venv/Scripts/python.exe scripts/run_issue_101_3.py \
    --eval-set docs/40_delivery/week3/model_test_assets/evaluation_set.json \
    --output logs/evaluation/issue_101_3_embedding_report.json \
    --collection civil_cases_v1 --device cpu
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings


@dataclass
class ChunkRow:
    row_id: str
    document: str
    metadata: Dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue #101-3 embedding/index runner")
    parser.add_argument(
        "--eval-set",
        type=str,
        required=True,
        help="Path to evaluation_set.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output report json",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="civil_cases_v1",
        help="Chroma collection name (fixed policy: civil_cases_v1)",
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=settings.CHROMA_DB_PATH,
        help="Chroma persist directory",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=settings.EMBEDDING_MODEL,
        help="SentenceTransformers model name",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda", "mps"],
        help="Embedding device",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Initial embedding batch size",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and recreate collection before indexing",
    )
    return parser.parse_args()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_timestamp() -> int:
    """Unix timestamp for compatibility with ChromaDB numeric filters."""
    return int(datetime.now(timezone.utc).timestamp())


def _load_eval_set(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("evaluation_set must be a list")
    return payload


def _normalize_rows(cases: List[Dict[str, Any]]) -> Tuple[List[ChunkRow], Dict[str, int]]:
    rows: List[ChunkRow] = []
    skipped = 0

    for case_idx, case in enumerate(cases):
        if not isinstance(case, dict):
            skipped += 1
            continue

        benchmark_case_id = str(case.get("case_id") or f"BENCHX-{case_idx + 1:04d}")
        scenario_type = str(case.get("scenario_type") or "multi_request")
        risk_level = str(case.get("risk_level") or "unknown")
        time_sensitivity = str(case.get("time_sensitivity") or "unknown")
        requires_multi = bool(case.get("requires_multi_request", False))
        query = str(case.get("query") or "").strip()

        context_items = case.get("context")
        if not isinstance(context_items, list) or not context_items:
            skipped += 1
            continue

        for chunk_idx, ctx in enumerate(context_items):
            if not isinstance(ctx, dict):
                continue

            chunk_id = str(ctx.get("chunk_id") or f"{benchmark_case_id}__chunk-{chunk_idx}")
            source_case_id = str(ctx.get("case_id") or "unknown")
            snippet = str(ctx.get("snippet") or "").strip()
            if not snippet:
                continue

            score = float(ctx.get("score", 0.0) or 0.0)
            # 계약 필드 기준으로 최소 메타데이터 세트 유지
            # created_at: Unix timestamp for ChromaDB numeric range filters ($gte, $lte)
            metadata = {
                "case_id": source_case_id,
                "chunk_id": chunk_id,
                "source": "week3_evaluation_set",
                "created_at": _now_timestamp(),
                "category": scenario_type,
                "region": "unknown",
                "benchmark_case_id": benchmark_case_id,
                "scenario_type": scenario_type,
                "risk_level": risk_level,
                "time_sensitivity": time_sensitivity,
                "requires_multi_request": str(requires_multi).lower(),
                "query": query[:300],
                "seed_score": score,
            }
            unique_row_id = f"{benchmark_case_id}::{chunk_id}"

            # 평가셋 질의와 근거 청크를 함께 색인해 retrieval 지표 측정 시
            # 질의-근거 정렬 신호를 강화한다.
            if query:
                document_text = f"질의: {query}\n근거: {snippet}"
            else:
                document_text = snippet

            rows.append(
                ChunkRow(
                    row_id=unique_row_id,
                    document=document_text,
                    metadata=metadata,
                )
            )

    stats = {
        "input_cases": len(cases),
        "normalized_chunks": len(rows),
        "skipped_cases": skipped,
    }
    return rows, stats


def _embed_documents(
    model_name: str,
    device: str,
    docs: List[str],
    batch_size: int,
) -> Tuple[List[List[float]], Dict[str, Any]]:
    from sentence_transformers import SentenceTransformer

    start = time.perf_counter()
    model = SentenceTransformer(model_name, device=device)

    current_batch = max(1, int(batch_size))
    retries = 0
    max_retries = 3

    while True:
        try:
            vectors = model.encode(
                docs,
                batch_size=current_batch,
                normalize_embeddings=True,
                show_progress_bar=True,
                convert_to_numpy=True,
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            info = {
                "embedding_model": model_name,
                "device": device,
                "batch_size": current_batch,
                "dimension": int(vectors.shape[1]) if len(vectors.shape) == 2 else 0,
                "elapsed_ms": elapsed_ms,
                "retries": retries,
            }
            return vectors.tolist(), info
        except RuntimeError as exc:
            message = str(exc).lower()
            if "out of memory" not in message or retries >= max_retries or current_batch == 1:
                raise
            retries += 1
            current_batch = max(1, current_batch // 2)


def _upsert_chroma(
    persist_dir: str,
    collection_name: str,
    rebuild: bool,
    rows: List[ChunkRow],
    embeddings: List[List[float]],
) -> Dict[str, Any]:
    import chromadb

    persist_path = Path(persist_dir)
    persist_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist_path))

    if rebuild:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(name=collection_name)

    ids = [row.row_id for row in rows]
    documents = [row.document for row in rows]
    metadatas = [row.metadata for row in rows]

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return {
        "collection_name": collection_name,
        "persist_dir": str(persist_path),
        "collection_count": int(collection.count()),
    }


def _write_report(path: Path, report: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    t0 = time.perf_counter()

    eval_path = Path(args.eval_set)
    output_path = Path(args.output)

    if args.collection != "civil_cases_v1":
        print("[WARN] collection name policy is civil_cases_v1. overriding.")
        args.collection = "civil_cases_v1"

    try:
        cases = _load_eval_set(eval_path)
        rows, norm_stats = _normalize_rows(cases)

        if not rows:
            raise RuntimeError("No rows prepared for indexing")

        docs = [row.document for row in rows]
        embeddings, emb_info = _embed_documents(
            model_name=args.embedding_model,
            device=args.device,
            docs=docs,
            batch_size=args.batch_size,
        )

        chroma_info = _upsert_chroma(
            persist_dir=args.persist_dir,
            collection_name=args.collection,
            rebuild=args.rebuild,
            rows=rows,
            embeddings=embeddings,
        )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        chunk_count = len(rows)
        indexed_case_count = max(0, norm_stats["input_cases"] - norm_stats["skipped_cases"])
        failed_count = max(0, norm_stats["input_cases"] - indexed_case_count)

        report = {
            "status": "success",
            "generated_at": _now_iso(),
            "input": {
                "eval_set": str(eval_path),
                "cases": norm_stats["input_cases"],
            },
            "normalization": norm_stats,
            "embedding": emb_info,
            "indexing": {
                "indexed_count": indexed_case_count,
                "chunk_count": chunk_count,
                "failed_count": failed_count,
                "success_rate": round(indexed_case_count / max(1, norm_stats["input_cases"]), 4),
                "elapsed_ms": elapsed_ms,
                **chroma_info,
            },
            "gate": {
                "issue": "101-3",
                "target_indexed_count": 495,
                "passed": indexed_case_count >= 495,
            },
        }

        _write_report(output_path, report)

        print("[OK] indexing complete")
        print(f"[OK] cases={indexed_case_count}/{norm_stats['input_cases']} chunks={chunk_count}")
        print(f"[OK] collection={chroma_info['collection_name']} count={chroma_info['collection_count']}")
        print(f"[OK] report={output_path}")
        return 0

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        report = {
            "status": "failed",
            "generated_at": _now_iso(),
            "error": str(exc),
            "elapsed_ms": elapsed_ms,
            "input": {
                "eval_set": str(eval_path),
                "collection": args.collection,
            },
        }
        _write_report(output_path, report)
        print(f"[ERROR] {exc}")
        print(f"[INFO] failure report saved: {output_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

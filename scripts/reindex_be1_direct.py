"""BE1 최신 구조화로 civil_cases 직접 재색인 (서버 없이 in-process).

#369 후속. ENABLE_RESPONSIBLE_UNIT=true 로 원천 9,132건을 최신 BE1 구조화 파이프라인에
태워 responsible_unit(name/source/confidence)을 생성하고, RetrievalService.index_documents 를
직접 호출해 새 컬렉션에 색인한다(REST 서버 경유 안 함 → 갱신된 색인 코드 사용, DB 단독 접근).

스트리밍 배치: 구조화→색인을 배치 단위로 흘려보내 메모리 절약 + 진행률/부분결과 확보.
실행 예:
  ENABLE_RESPONSIBLE_UNIT=true OLLAMA_BASE_URL=http://100.71.35.78:11434 \
  STRUCTURING_MODEL=exaone3.5:7.8b \
  python3 scripts/reindex_be1_direct.py --collection-name civil_cases_v2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import pipeline_logger
from app.ingestion.service import get_ingestion_service
from app.structuring.service import get_structuring_service
from app.retrieval.service import get_retrieval_service
from scripts.build_index import _build_api_case_record


def _existing_case_ids(collection_name: str) -> set[str]:
    """대상 컬렉션에 이미 색인된 case_id 집합 (resume 용)."""
    import chromadb
    client = chromadb.PersistentClient(path=str(PROJECT_ROOT / "data" / "chroma_db"))
    if collection_name not in [c.name for c in client.list_collections()]:
        return set()
    metas = client.get_collection(collection_name).get(include=["metadatas"])["metadatas"]
    return {str(m.get("case_id") or "") for m in metas}


def _read_normalized_items(json_files: list[Path], ingestion_svc, exclude_case_ids: set[str] | None = None) -> list[dict[str, Any]]:
    exclude = exclude_case_ids or set()
    skipped = 0
    items: list[dict[str, Any]] = []
    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                if exclude and f"CASE-{item.get('source_id') or ''}" in exclude:
                    skipped += 1
                    continue
                if "consulting_content" in item or "consulting_date" in item:
                    items.append(ingestion_svc.normalize_aihub_record(item, source_file=str(file_path)))
                else:
                    items.append({
                        "case_id": item.get("case_id") or item.get("id") or "",
                        "source": item.get("source") or "unknown",
                        "source_id": item.get("source_id") or "",
                        "created_at": item.get("created_at") or item.get("submitted_at") or "",
                        "submitted_at": item.get("submitted_at") or "",
                        "category": item.get("category") or item.get("consulting_category") or "unknown",
                        "region": item.get("region") or "unknown",
                        "raw_text": item.get("raw_text") or item.get("text") or "",
                        "text": item.get("text") or "",
                        "metadata": item.get("metadata") or {},
                    })
        except Exception as e:  # noqa: BLE001
            pipeline_logger.error(f"파일 처리 오류 ({file_path}): {e}")
    if exclude:
        pipeline_logger.info(f"resume: 이미 색인된 {skipped}건 건너뜀")
    return items


async def main(input_dir: str, collection_name: str, batch_size: int, rebuild: bool, limit: int, resume: bool = False) -> None:
    logger = pipeline_logger
    ingestion_svc = get_ingestion_service()
    structuring_svc = get_structuring_service()
    retrieval_svc = get_retrieval_service()

    data_dir = Path(input_dir)
    if not data_dir.exists():
        logger.error(f"입력 디렉토리 없음: {data_dir}")
        sys.exit(1)
    json_files = sorted(data_dir.rglob("*.json"))
    if limit > 0:
        json_files = json_files[:limit]

    exclude_case_ids: set[str] = set()
    if resume:
        exclude_case_ids = _existing_case_ids(collection_name)
        rebuild = False  # 이어하기는 절대 컬렉션을 비우지 않는다
        logger.info(f"resume 모드: '{collection_name}' 기존 {len(exclude_case_ids)}건 보존, 나머지만 색인")
    logger.info(f"재색인 시작. 원천 파일 {len(json_files)}개 → 컬렉션 '{collection_name}' (rebuild={rebuild})")

    normalized_list = await ingestion_svc.process(
        _read_normalized_items(json_files, ingestion_svc, exclude_case_ids=exclude_case_ids)
    )
    total_docs = len(normalized_list)
    logger.info(f"정제 완료 {total_docs}건. 구조화→색인 시작.")

    batch: list[Dict[str, Any]] = []
    indexed = 0
    failed = 0
    first_batch = True
    t0 = time.time()

    async def flush() -> None:
        nonlocal batch, indexed, first_batch
        if not batch:
            return
        await retrieval_svc.index_documents(
            documents=batch,
            rebuild=(first_batch and rebuild),
            collection_name=collection_name,
        )
        indexed += len(batch)
        first_batch = False
        elapsed = time.time() - t0
        rate = indexed / elapsed if elapsed else 0.0
        eta = (total_docs - indexed) / rate / 60 if rate else 0.0
        print(f"[index] {indexed}/{total_docs} 색인 ({elapsed:.0f}s, {rate:.1f}건/s, ETA {eta:.0f}분, 실패 {failed})", flush=True)
        batch = []

    for normalized in normalized_list:
        try:
            if normalized.get("text"):
                normalized["raw_text"] = normalized["text"]
            structured = await structuring_svc.structure(normalized)
            batch.append(_build_api_case_record(normalized, structured))
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.error(f"구조화 실패(skip) case={normalized.get('case_id')}: {e}")
        if len(batch) >= batch_size:
            await flush()
    await flush()

    logger.info(f"재색인 완료: 색인 {indexed}건, 실패 {failed}건 → '{collection_name}' ({time.time()-t0:.0f}s)")
    print(f"[done] indexed={indexed} failed={failed} collection={collection_name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BE1 최신 구조화 기반 직접 재색인")
    parser.add_argument("--input-dir", default="data/Public_Civil_Service_LLM_Data")
    parser.add_argument("--collection-name", default="civil_cases_v2")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--rebuild", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true", help="대상 컬렉션의 기존 case_id 는 건너뛰고 이어서 색인(미완성 재색인 복구)")
    args = parser.parse_args()
    asyncio.run(main(args.input_dir, args.collection_name, args.batch_size, args.rebuild, args.limit, args.resume))

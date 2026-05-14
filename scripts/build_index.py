"""
벡터 인덱스 빌드 스크립트 (PR #204 하이브리드 구조화 반영)

원천 데이터(Civil_complaints_data)를 읽어 전처리, 구조화를 거친 후
BE2의 REST 인덱싱 계약(/api/v1/index)으로 전달합니다.

Usage:
    python scripts/build_index.py --input-dir data/Civil_complaints_data
"""

import sys
import argparse
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import httpx

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import pipeline_logger
from app.ingestion.service import get_ingestion_service
from app.structuring.service import get_structuring_service


def _build_api_case_record(normalized: Dict[str, Any], structured: Dict[str, Any]) -> Dict[str, Any]:
    obs_text = structured.get("observation", {}).get("text", "")
    res_text = structured.get("result", {}).get("text", "")
    req_text = structured.get("request", {}).get("text", "")
    ctx_text = structured.get("context", {}).get("text", "")

    entities = structured.get("entities", [])

    combined_text = (
        f"[원문]\n{normalized['text']}\n"
        f"[관찰]\n{obs_text}\n"
        f"[결과]\n{res_text}\n"
        f"[요청]\n{req_text}\n"
        f"[배경]\n{ctx_text}"
    )

    metadata: Dict[str, Any] = {
        "case_id": structured["case_id"],
        "source": structured["source"],
        "category": structured["category"],
        "region": structured.get("region") or normalized.get("region"),
        "created_at": structured.get("created_at"),
        "structured_by": structured.get("structured_by", "fallback"),
        "is_valid": structured.get("validation", {}).get("is_valid", False),
    }

    return {
        "case_id": structured["case_id"],
        "id": structured["case_id"],
        "source": structured["source"],
        "created_at": structured.get("created_at"),
        "submitted_at": normalized.get("submitted_at"),
        "category": structured["category"],
        "region": structured.get("region") or normalized.get("region"),
        "text": combined_text,
        "structured_text": {
            "observation": obs_text,
            "result": res_text,
            "request": req_text,
            "context": ctx_text,
        },
        "observation": {"text": obs_text},
        "result": {"text": res_text},
        "request": {"text": req_text},
        "context": {"text": ctx_text},
        "entities": entities,
        "metadata": metadata,
    }


async def _index_via_rest_api(
    *,
    api_url: str,
    cases: list[Dict[str, Any]],
    collection_name: str,
    batch_size: int,
    rebuild: bool,
    logger,
) -> None:
    endpoint = f"{api_url.rstrip('/')}/api/v1/index"
    effective_batch_size = max(1, int(batch_size))
    total_batches = (len(cases) + effective_batch_size - 1) // effective_batch_size
    total_indexed = 0
    total_failed = 0

    async with httpx.AsyncClient(timeout=600.0) as client:
        for batch_number, start_index in enumerate(range(0, len(cases), effective_batch_size), start=1):
            batch = cases[start_index : start_index + effective_batch_size]
            action = "bulk" if (batch_number == 1 and rebuild) else "incremental"
            request_id = f"IDX-{datetime.now().strftime('%Y%m%d%H%M%S')}-{batch_number:03d}"

            payload = {
                "request_id": request_id,
                "action": action,
                "collection_name": collection_name,
                "cases": batch,
            }

            logger.info(
                "BE2 인덱싱 요청 전송: batch=%d/%d action=%s cases=%d collection=%s endpoint=%s",
                batch_number,
                total_batches,
                action,
                len(batch),
                collection_name,
                endpoint,
            )

            response = await client.post(endpoint, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "BE2 인덱싱 실패: batch=%d/%d status=%s response=%s",
                    batch_number,
                    total_batches,
                    response.status_code,
                    response.text,
                )
                raise RuntimeError(f"BE2 인덱싱 실패: {exc}") from exc

            body = response.json()
            if not body.get("success", False):
                logger.error(
                    "BE2 인덱싱 응답 실패: batch=%d/%d body=%s",
                    batch_number,
                    total_batches,
                    body,
                )
                raise RuntimeError(f"BE2 인덱싱 응답 실패: {body}")

            data = body.get("data", {}) if isinstance(body.get("data", {}), dict) else {}
            indexed_count = int(data.get("indexed_count", 0))
            failed_count = int(data.get("failed_count", 0))
            total_indexed += indexed_count
            total_failed += failed_count

            logger.info(
                "BE2 인덱싱 완료: batch=%d/%d indexed=%d failed=%d collection=%s",
                batch_number,
                total_batches,
                indexed_count,
                failed_count,
                collection_name,
            )

    logger.info(
        "BE2 REST 인덱싱 전체 완료: total_cases=%d indexed=%d failed=%d collection=%s",
        len(cases),
        total_indexed,
        total_failed,
        collection_name,
    )


async def main(input_dir: str, api_url: str, collection_name: str, batch_size: int, rebuild: bool):
    logger = pipeline_logger
    ingestion_svc = get_ingestion_service()
    structuring_svc = get_structuring_service()
    
    data_dir = Path(input_dir)
    if not data_dir.exists():
        logger.error(f"Cannot find input directory: {data_dir}")
        sys.exit(1)
        
    json_files = list(data_dir.rglob("*.json"))
    logger.info(f"인덱싱 시작. 찾은 JSON 파일 수: {len(json_files)}")

    docs_to_index = []
    normalized_items = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # JSON 파일이 리스트인 경우와 단일 딕셔너리인 경우 모두 처리
            if isinstance(data, dict):
                data = [data]

            for item in data:
                # AI Hub 원천데이터 정규화 (필드 호환 보장)
                if "consulting_content" in item or "consulting_date" in item:
                    normalized_items.append(
                        ingestion_svc.normalize_aihub_record(item, source_file=str(file_path))
                    )
                else:
                    normalized_items.append({
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
                        "instructions": item.get("instructions") if isinstance(item.get("instructions"), list) else [],
                    })

        except Exception as e:
            logger.error(f"파일 처리 중 오류 발생 ({file_path}): {e}")

    # 1. Ingestion 전처리 (clean + mask + global dedup)
    normalized_list = await ingestion_svc.process(normalized_items)

    for normalized in normalized_list:
        # 구조화 입력은 정제/마스킹된 텍스트로 맞춘다.
        if normalized.get("text"):
            normalized["raw_text"] = normalized["text"]

        # 2. Structuring 수행 (하이브리드 아키텍처)
        structured = await structuring_svc.structure(normalized)

        api_case_record = _build_api_case_record(normalized, structured)
        docs_to_index.append(api_case_record)

        obs_text = api_case_record["structured_text"]["observation"]
        res_text = api_case_record["structured_text"]["result"]
        req_text = api_case_record["structured_text"]["request"]
        ctx_text = api_case_record["structured_text"]["context"]

        # 터미널에 구조화 및 적재 대기 데이터 출력
        structured_by = structured.get("structured_by", "unknown")
        confidence = structured.get("confidence_score", 0.0)
        validation = structured.get("validation", {})
        warnings = validation.get("warnings", [])

        print(f"\n[{len(docs_to_index)}번째 처리 완료] ID: {api_case_record['case_id']}")
        print(f"--- [Metadata 요약] ---")
        print(f"Category: {api_case_record['category']}")
        print(f"structured_by={structured_by}, confidence={confidence:.2f}")
        if warnings:
            print(f"[WARN] {', '.join(warnings)}")
        print(f"Observation: {obs_text[:100]}..." if len(obs_text) > 100 else f"Observation: {obs_text}")
        print(f"Result: {res_text[:100]}..." if len(res_text) > 100 else f"Result: {res_text}")
        print(f"Request: {req_text[:100]}..." if len(req_text) > 100 else f"Request: {req_text}")
        print(f"Context: {ctx_text[:100]}..." if len(ctx_text) > 100 else f"Context: {ctx_text}")
        print("-----------------------\n")

    logger.info(f"변환 완료. 총 문서 수: {len(docs_to_index)}. BE2 REST 인덱싱 진행 중...")
    
    if len(docs_to_index) > 0:
        try:
            await _index_via_rest_api(
                api_url=api_url,
                cases=docs_to_index,
                collection_name=collection_name,
                batch_size=batch_size,
                rebuild=rebuild,
                logger=logger,
            )
        except Exception as e:
            logger.error(f"BE2 REST 인덱싱 중 오류 발생: {e}")
            sys.exit(1)
    else:
        logger.warning("인덱싱할 문서를 찾지 못했습니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="벡터 인덱스 빌드 (Hybrid 형식)")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/Civil_complaints_data",
        help="입력 원천 데이터 디렉토리 경로",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://127.0.0.1:8000",
        help="BE2 REST API 기본 URL",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default="civil_cases_v1",
        help="인덱싱 컬렉션 이름",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="BE2 REST 인덱싱 배치 크기",
    )
    parser.add_argument(
        "--rebuild",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="True(기본값): 1번 배치에서 컬렉션 초기화 후 재빌드. --no-rebuild: 전체 incremental 추가",
    )
    args = parser.parse_args()

    asyncio.run(main(args.input_dir, args.api_url, args.collection_name, args.batch_size, args.rebuild))

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
    obs = structured.get("observation", {})
    res = structured.get("result", {})
    req = structured.get("request", {})
    ctx = structured.get("context", {})

    obs_text = obs.get("text", "")
    res_text = res.get("text", "")
    req_text = req.get("request", "") or req.get("text", "")
    ctx_text = ctx.get("text", "")

    entities = structured.get("entities", [])
    search_signals = {
        # BE2는 아래 선택 필드를 이미 soft rerank metadata로 해석할 수 있으므로
        # BE1 구조화 결과에서 누락 없이 보존한다.
        "entity_texts": structured.get("entity_texts", []),
        "issue_type": structured.get("issue_type", []),
        "legal_refs": structured.get("legal_refs", []),
        "key_terms": structured.get("key_terms", []),
        "responsible_unit": structured.get("responsible_unit", []),
        "urgency": structured.get("urgency", {}),
    }

    def _is_empty(text: str) -> bool:
        stripped = text.strip() if text else ""
        if not stripped:
            return True
        if stripped in ("없음", "해당없음", "없음.", "-", "N/A"):
            return True
        if stripped.lower() in ("null", "none", "n/a"):  # LLM 빈 요소 placeholder (issue #265)
            return True
        if stripped.startswith("없음 (") or stripped.startswith("없음("):
            return True
        return False

    # 임베딩 텍스트 = 라벨 없는 4요소 줄바꿈 결합 (운영 코퍼스 civil_cases_v1 및
    # 평가 쿼리 포맷과 동일). 과거에는 [원문] 전문 + [관찰]/[결과] 등 라벨을 포함했으나,
    # V3 100쿼리 A/B에서 [원문] 포함이 nDCG@5 −0.054, R@10 −0.091로 검색을 악화시켜
    # 제거했다. (#264, reports/retrieval/v3/risk264_raw_ab.json)
    parts = []
    if not _is_empty(obs_text):
        parts.append(obs_text)
    if not _is_empty(res_text):
        parts.append(res_text)
    if not _is_empty(req_text):
        parts.append(req_text)
    if not _is_empty(ctx_text):
        parts.append(ctx_text)
    combined_text = "\n".join(parts)

    metadata: Dict[str, Any] = {
        "case_id": structured["case_id"],
        "source": structured["source"],
        "category": structured["category"],
        "region": structured.get("region") or normalized.get("region"),
        "created_at": structured.get("created_at"),
        "structured_by": structured.get("structured_by", "fallback"),
        "is_valid": structured.get("validation", {}).get("is_valid", False),
    }

    def _field(raw: Dict[str, Any], text: str) -> Dict[str, Any]:
        field: Dict[str, Any] = {"text": text}
        if "confidence" in raw:
            field["confidence"] = raw["confidence"]
        return field

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
            k: v for k, v in {
                "observation": obs_text,
                "result": res_text,
                "request": req_text,
                "context": ctx_text,
            }.items() if not _is_empty(v)
        },
        "observation": _field(obs, obs_text) if not _is_empty(obs_text) else {},
        "result": _field(res, res_text) if not _is_empty(res_text) else {},
        "request": _field(req, req_text) if not _is_empty(req_text) else {},
        "context": _field(ctx, ctx_text) if not _is_empty(ctx_text) else {},
        "entities": entities,
        **search_signals,
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


async def main(input_dir: str, api_url: str, collection_name: str, batch_size: int, rebuild: bool, limit: int = 0):
    logger = pipeline_logger
    ingestion_svc = get_ingestion_service()
    structuring_svc = get_structuring_service()
    
    data_dir = Path(input_dir)
    if not data_dir.exists():
        logger.error(f"Cannot find input directory: {data_dir}")
        sys.exit(1)
        
    json_files = list(data_dir.rglob("*.json"))
    if limit > 0:
        json_files = json_files[:limit]
    logger.info(f"인덱싱 시작. 찾은 JSON 파일 수: {len(json_files)}{f' (limit={limit})' if limit > 0 else ''}")

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

        obs_text = api_case_record["structured_text"].get("observation", "")
        res_text = api_case_record["structured_text"].get("result", "")
        req_text = api_case_record["structured_text"].get("request", "")
        ctx_text = api_case_record["structured_text"].get("context", "")

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
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="처리할 최대 JSON 파일 수 (0: 제한 없음)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.input_dir, args.api_url, args.collection_name, args.batch_size, args.rebuild, args.limit))

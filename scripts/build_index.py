"""
벡터 인덱스 빌드 스크립트 (PR #204 하이브리드 구조화 반영)

원천 데이터(Civil_complaints_data)를 읽어 전처리, 구조화를 거친 후
평탄화된 메타데이터와 함께 ChromaDB에 저장합니다.

Usage:
    python scripts/build_index.py --input-dir data/Civil_complaints_data
"""

import sys
import argparse
import json
import asyncio
from pathlib import Path
from typing import Dict, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import pipeline_logger
from app.ingestion.service import get_ingestion_service
from app.structuring.service import get_structuring_service
from app.retrieval.service import get_retrieval_service


async def main(input_dir: str):
    logger = pipeline_logger
    ingestion_svc = get_ingestion_service()
    structuring_svc = get_structuring_service()
    retrieval_svc = get_retrieval_service()
    
    data_dir = Path(input_dir)
    if not data_dir.exists():
        logger.error(f"Cannot find input directory: {data_dir}")
        sys.exit(1)
        
    json_files = list(data_dir.rglob("*.json"))
    logger.info(f"인덱싱 시작. 찾은 JSON 파일 수: {len(json_files)}")

    docs_to_index = []
    
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # JSON 파일이 리스트인 경우와 단일 딕셔너리인 경우 모두 처리
            if isinstance(data, dict):
                data = [data]
                
            for item in data:
                # 1. Ingestion 전처리
                normalized_list = await ingestion_svc.process([item])
                normalized = normalized_list[0]
                
                # 2. Structuring 수행 (하이브리드 아키텍처)
                structured = await structuring_svc.structure(normalized)
                
                # 3. ChromaDB 제약에 맞춘 Metadata 평탄화
                # 4요소를 text 형태로 추출 (딕셔너리 형태 불가)
                obs_text = structured.get("observation", {}).get("text", "")
                res_text = structured.get("result", {}).get("text", "")
                req_text = structured.get("request", {}).get("text", "")
                ctx_text = structured.get("context", {}).get("text", "")
                
                # Entities는 리스트/딕셔너리이므로 JSON 문자열로 직렬화
                entities_str = json.dumps(structured.get("entities", []), ensure_ascii=False)
                
                # ChromaDB 문서 본문 (검색 시 중요한 컨텍스트를 담도록 조합)
                # (원문 normalized["text"]를 넣어도 되고, 아래처럼 구조화된 텍스트를 넣어도 됨. 여기선 결합 텍스트 사용)
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
                    "observation": obs_text,
                    "result": res_text,
                    "request": req_text,
                    "context": ctx_text,
                    "entities": entities_str,
                    "structured_by": structured.get("structured_by", "fallback"),
                    "is_valid": structured.get("validation", {}).get("is_valid", False),
                }
                
                docs_to_index.append({
                    "id": structured["case_id"],
                    "text": combined_text,
                    "metadata": metadata
                })
                
        except Exception as e:
            logger.error(f"파일 처리 중 오류 발생 ({file_path}): {e}")

    logger.info(f"변환 완료. 총 문서 수: {len(docs_to_index)}. ChromaDB Upsert 진행 중...")
    
    if len(docs_to_index) > 0:
        try:
            # 4. ChromaDB에 인덱싱
            res = await retrieval_svc.index_documents(
                documents=docs_to_index, 
                rebuild=True,
                collection_name="civil_cases_v1"
            )
            logger.info(f"인덱싱 완료: {res}")
        except Exception as e:
            logger.error(f"ChromaDB Upsert 중 오류 발생: {e}")
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
    args = parser.parse_args()

    asyncio.run(main(args.input_dir))

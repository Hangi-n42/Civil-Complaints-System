"""
벡터 인덱스 빌드 스크립트

원본 데이터를 벡터로 변환하여 ChromaDB에 저장한다.

Usage:
    python scripts/build_index.py --input data/raw/samples.json
"""

import sys
import argparse
import json
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import pipeline_logger
from app.ingestion.service import get_ingestion_service
from app.structuring.service import get_structuring_service
from app.retrieval.service import get_retrieval_service


async def main(input_file: str):
    """메인 함수"""
    logger = pipeline_logger

    try:
        logger.info(f"인덱스 빌드 시작: {input_file}")

        # 입수 서비스
        ingestion_svc = get_ingestion_service()

        # 구조화 서비스
        structuring_svc = get_structuring_service()

        # 검색 서비스
        retrieval_svc = get_retrieval_service()

        # TODO: 실제 파이프라인 구현
        # 1. 데이터 로드 (ingestion_svc.load_json)
        # 2. 전처리 (ingestion_svc.process)
        # 3. 구조화 (structuring_svc.structure)
        # 4. 청킹 및 임베딩 (retrieval_svc.chunk_text, embed_texts)
        # 5. 인덱싱 (retrieval_svc.index_documents)

        logger.info("인덱스 빌드 완료")

    except Exception as e:
        logger.error(f"인덱스 빌드 실패: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="벡터 인덱스 빌드")
    parser.add_argument(
        "--input",
        type=str,
        default="data/raw/samples.json",
        help="입력 파일 경로",
    )
    args = parser.parse_args()

    import asyncio

    asyncio.run(main(args.input))

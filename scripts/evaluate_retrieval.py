"""
평가 스크립트 - 검색 평가

검색 시스템의 성능을 평가한다.

Usage:
    python scripts/evaluate_retrieval.py --queries data/annotations/queries.json
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import evaluation_logger


def main(queries_file: str, system_file: str, output_file: str):
    """메인 함수"""
    logger = evaluation_logger

    try:
        logger.info(f"검색 평가 시작: queries={queries_file}, system={system_file}")

        # TODO: 평가 로직 구현
        # 1. 쿼리 로드
        # 2. 검색 수행
        # 3. MRR, NDCG, MAP@k 계산
        # 4. 결과 리포트 생성
        # 5. output_file 저장

        logger.info(f"검색 평가 완료: 결과 파일={output_file}")

    except Exception as e:
        logger.error(f"검색 평가 실패: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="검색 평가")
    parser.add_argument(
        "--queries",
        type=str,
        default="data/annotations/queries.json",
        help="쿼리 파일 경로",
    )
    parser.add_argument(
        "--system",
        type=str,
        required=True,
        help="시스템 검색 결과 파일 경로",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/annotations/retrieval_eval_result.json",
        help="평가 결과 출력 경로",
    )
    args = parser.parse_args()

    main(args.queries, args.system, args.output)

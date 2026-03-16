"""
평가 스크립트 - 구조화 평가

구조화된 데이터의 정확도를 평가한다.

Usage:
    python scripts/evaluate_structuring.py --gold data/annotations/gold.json
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import evaluation_logger


def main(gold_file: str):
    """메인 함수"""
    logger = evaluation_logger

    try:
        logger.info(f"구조화 평가 시작: {gold_file}")

        # TODO: 평가 로직 구현
        # 1. 정답 데이터 로드
        # 2. 예측 데이터 로드
        # 3. Precision, Recall, F1 계산
        # 4. 결과 리포트 생성

        logger.info("구조화 평가 완료")

    except Exception as e:
        logger.error(f"구조화 평가 실패: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="구조화 평가")
    parser.add_argument(
        "--gold",
        type=str,
        default="data/annotations/gold.json",
        help="정답 데이터 파일 경로",
    )
    args = parser.parse_args()

    main(args.gold)

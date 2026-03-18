"""
평가 스크립트 - QA 평가

질의응답 시스템의 성능을 평가한다.

Usage:
    python scripts/evaluate_qa.py --gold data/annotations/qa_gold.json
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import evaluation_logger


def main(gold_file: str, pred_file: str, output_file: str):
    """메인 함수"""
    logger = evaluation_logger

    try:
        logger.info(f"QA 평가 시작: gold={gold_file}, pred={pred_file}")

        # TODO: 평가 로직 구현
        # 1. 정답 데이터 로드
        # 2. QA 수행
        # 3. BLEU, ROUGE, F1 계산
        # 4. Citation 정확성 평가
        # 5. 결과 리포트 생성
        # 6. output_file 저장

        logger.info(f"QA 평가 완료: 결과 파일={output_file}")

    except Exception as e:
        logger.error(f"QA 평가 실패: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="QA 평가")
    parser.add_argument(
        "--gold",
        type=str,
        default="data/annotations/qa_gold.json",
        help="정답 데이터 파일 경로",
    )
    parser.add_argument(
        "--pred",
        type=str,
        required=True,
        help="QA 예측 결과 파일 경로",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/annotations/qa_eval_result.json",
        help="평가 결과 출력 경로",
    )
    args = parser.parse_args()

    main(args.gold, args.pred, args.output)

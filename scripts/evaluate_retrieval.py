"""
평가 스크립트 - 검색 평가

검색 시스템의 성능을 평가한다.

Usage:
    python scripts/evaluate_retrieval.py --queries data/annotations/queries.json
"""

import sys
import json
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import evaluation_logger
from scripts.run_issue_103 import (
    _load_eval_set,
    _extract_queries,
    _initialize_chroma_client,
    _initialize_embedding_model,
    _evaluate_single_query,
)


def main(queries_file: str, system_file: str, output_file: str):
    """메인 함수"""
    logger = evaluation_logger

    try:
        logger.info(f"검색 평가 시작: queries={queries_file}, system={system_file}")

        eval_set = _load_eval_set(Path(queries_file))
        queries = _extract_queries(eval_set, sample_size=0)

        _, collection = _initialize_chroma_client(
            persist_dir=str(project_root / "data" / "chroma_db"),
            collection_name="civil_cases_v1",
        )
        model = _initialize_embedding_model("BAAI/bge-m3", "cpu")

        rows = []
        for query_id, query_text, ground_truth in queries:
            rows.append(
                _evaluate_single_query(
                    query_id=query_id,
                    query_text=query_text,
                    ground_truth=ground_truth,
                    collection=collection,
                    model=model,
                    top_k=10,
                )
            )

        total = len(rows)
        recall_at_5 = sum(r.recall_at_5 for r in rows) / total if total else 0.0
        recall_at_10 = sum(r.recall_at_10 for r in rows) / total if total else 0.0
        mrr_at_5 = sum(r.mrr_at_5 for r in rows) / total if total else 0.0
        mrr_at_10 = sum(r.mrr_at_10 for r in rows) / total if total else 0.0
        avg_latency_ms = sum(r.latency_ms for r in rows) / total if total else 0.0

        report = {
            "status": "success",
            "total_queries": total,
            "recall_5": round(recall_at_5, 4),
            "recall_10": round(recall_at_10, 4),
            "mrr_5": round(mrr_at_5, 4),
            "mrr_10": round(mrr_at_10, 4),
            "avg_latency_ms": round(avg_latency_ms, 2),
            "gate": {
                "recall_5": {"target": 0.75, "passed": recall_at_5 >= 0.75},
                "avg_latency_ms": {"target": 12000, "passed": avg_latency_ms <= 12000},
            },
        }

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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

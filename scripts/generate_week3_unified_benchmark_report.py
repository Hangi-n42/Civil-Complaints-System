"""Week3 unified benchmark report generator.

Usage:
  python scripts/generate_week3_unified_benchmark_report.py \
    --input-dir logs/evaluation/week3 \
    --output logs/evaluation/week3/model_benchmark_report_final.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_candidate_reports(input_dir: Path) -> Dict[str, Path]:
    """model_benchmark_candidate_*.json 파일들을 찾는다."""
    reports = {}
    for json_file in sorted(input_dir.glob("model_benchmark_candidate_*.json")):
        model_id = json_file.stem.replace("model_benchmark_candidate_", "")
        reports[model_id] = json_file
    return reports


def _extract_summary_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """개별 리포트에서 summary를 추출한다."""
    summaries = {row.get("model_id", ""): row for row in report.get("summary", [])}
    return summaries


def _calculate_ranked_metrics(reports: Dict[str, Path]) -> Dict[str, Any]:
    """모든 리포트를 읽어서 순위/점수를 계산한다."""
    all_summaries = {}
    
    for model_id, report_path in reports.items():
        try:
            report = _read_json(report_path)
            summaries = _extract_summary_from_report(report)
            for mid, summary in summaries.items():
                if summary.get("status") == "measured":
                    all_summaries[mid] = {
                        "model_id": summary.get("model_id"),
                        "model_name": summary.get("model_name"),
                        "status": "measured",
                        "parse_success_rate": float(summary.get("parse_success_rate", 0.0)),
                        "answer_non_empty_rate": float(summary.get("answer_non_empty_rate", 0.0)),
                        "citation_match_rate": float(summary.get("citation_match_rate", 0.0)),
                        "avg_latency_sec": float(summary.get("avg_latency_sec", 999.0)) if summary.get("avg_latency_sec") else 999.0,
                        "p95_latency_sec": float(summary.get("p95_latency_sec", 999.0)) if summary.get("p95_latency_sec") else 999.0,
                    }
        except Exception as e:
            print(f"[ERROR] 리포트 읽기 실패 {report_path}: {e}")
            continue
    
    # 점수 계산 (가중치: parse=0.3, answer=0.2, citation=0.3, latency=0.2)
    for model_id, metrics in all_summaries.items():
        # Latency 정규화 (작을수록 좋음) - 최대값 기준으로 normalization
        max_latency = max(
            m["avg_latency_sec"] 
            for m in all_summaries.values() 
            if m.get("avg_latency_sec", 0) < 999
        ) or 12.0
        latency_score = max(0.0, 1.0 - (metrics["avg_latency_sec"] / max_latency))
        
        # 종합 점수
        composite_score = (
            metrics["parse_success_rate"] * 0.3 +
            metrics["answer_non_empty_rate"] * 0.2 +
            metrics["citation_match_rate"] * 0.3 +
            latency_score * 0.2
        )
        
        metrics["composite_score"] = round(composite_score, 4)
        metrics["latency_score"] = round(latency_score, 4)
    
    # 점수순 정렬
    ranked = sorted(
        all_summaries.items(),
        key=lambda x: x[1].get("composite_score", 0.0),
        reverse=True
    )
    
    return {
        "measured_models": all_summaries,
        "ranked": [(mid, metrics) for mid, metrics in ranked],
    }


def _recommend_baseline(ranked_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """합격 기준에 따라 baseline을 추천한다."""
    # 합격 기준 (Week3 1차):
    # - parse_success_rate >= 0.9
    # - citation_match_rate >= 0.8
    # - avg_latency_sec <= 12
    
    candidates = []
    for model_id, metrics in ranked_metrics.get("measured_models", {}).items():
        passes_criteria = (
            metrics["parse_success_rate"] >= 0.9 and
            metrics["citation_match_rate"] >= 0.8 and
            metrics["avg_latency_sec"] <= 12.0
        )
        if passes_criteria:
            candidates.append({
                "model_id": model_id,
                "model_name": metrics["model_name"],
                "composite_score": metrics["composite_score"],
                "parse_success_rate": metrics["parse_success_rate"],
                "citation_match_rate": metrics["citation_match_rate"],
                "avg_latency_sec": metrics["avg_latency_sec"],
            })
    
    # 점수순 정렬
    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    
    if candidates:
        recommendation = {
            "status": "found",
            "baseline_model_id": candidates[0]["model_id"],
            "baseline_model_name": candidates[0]["model_name"],
            "reason": f"합격 기준 만족, 종합 점수 {candidates[0]['composite_score']:.4f} (상위 {len(candidates)}개 후보 중 1순위)",
            "alternatives": candidates[1:3],  # 상위 2~3개 대안
        }
    else:
        # 합격 기준 미만시 최고점 모델 추천
        if ranked_metrics.get("ranked"):
            top_model_id, top_metrics = ranked_metrics["ranked"][0]
            recommendation = {
                "status": "conditional",
                "baseline_model_id": top_model_id,
                "baseline_model_name": top_metrics["model_name"],
                "reason": f"합격 기준 미만, 최고 종합 점수 {top_metrics['composite_score']:.4f} 모델 조건부 추천",
                "failing_metrics": {
                    "parse_success_rate": "< 0.9" if top_metrics["parse_success_rate"] < 0.9 else "OK",
                    "citation_match_rate": "< 0.8" if top_metrics["citation_match_rate"] < 0.8 else "OK",
                    "avg_latency_sec": "> 12" if top_metrics["avg_latency_sec"] > 12.0 else "OK",
                },
            }
        else:
            recommendation = {
                "status": "error",
                "reason": "측정된 모델 없음",
            }
    
    return recommendation


def main() -> None:
    parser = argparse.ArgumentParser(description="Week3 unified benchmark report generator")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="logs/evaluation/week3",
        help="개별 model_benchmark_candidate_*.json 파일들의 디렉터리",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="logs/evaluation/week3/model_benchmark_report_final.json",
        help="통합 리포트 출력 경로",
    )
    args = parser.parse_args()

    input_dir = (PROJECT_ROOT / args.input_dir).resolve()
    output_path = (PROJECT_ROOT / args.output).resolve()

    if not input_dir.exists():
        print(f"[ERROR] Input 디렉터리 없음: {input_dir}")
        return

    # 개별 리포트 찾기
    reports = _find_candidate_reports(input_dir)
    print(f"[INFO] Found {len(reports)} candidate reports: {list(reports.keys())}")

    if not reports:
        print("[WARN] model_benchmark_candidate_*.json 파일을 찾을 수 없음")
        return

    # 메트릭 계산
    ranked_metrics = _calculate_ranked_metrics(reports)
    
    # Baseline 추천
    recommendation = _recommend_baseline(ranked_metrics)

    # 최종 리포트 구성
    final_report = {
        "report_name": "Week3 Unified Model Benchmark Report",
        "generated_at": datetime.now().astimezone().isoformat(),
        "measured_models_count": len(ranked_metrics["measured_models"]),
        "summary_table": [
            {
                "rank": i + 1,
                "model_id": model_id,
                "model_name": metrics["model_name"],
                "status": metrics["status"],
                "composite_score": metrics["composite_score"],
                "parse_success_rate": metrics["parse_success_rate"],
                "answer_non_empty_rate": metrics["answer_non_empty_rate"],
                "citation_match_rate": metrics["citation_match_rate"],
                "avg_latency_sec": metrics["avg_latency_sec"],
                "p95_latency_sec": metrics["p95_latency_sec"],
                "latency_score": metrics.get("latency_score", 0.0),
            }
            for i, (model_id, metrics) in enumerate(ranked_metrics["ranked"])
        ],
        "baseline_recommendation": recommendation,
        "pass_criteria": {
            "parse_success_rate_min": 0.9,
            "citation_match_rate_min": 0.8,
            "avg_latency_sec_max": 12.0,
        },
        "score_weights": {
            "parse_success_rate": 0.3,
            "answer_non_empty_rate": 0.2,
            "citation_match_rate": 0.3,
            "latency_score": 0.2,
        },
    }

    # 출력
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(final_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[DONE] 통합 리포트 생성: {output_path}")
    print(f"\n[BASELINE RECOMMENDATION]")
    print(f"  Status: {recommendation['status']}")
    print(f"  Model: {recommendation.get('baseline_model_name', 'N/A')}")
    print(f"  Reason: {recommendation.get('reason', 'N/A')}")


if __name__ == "__main__":
    main()

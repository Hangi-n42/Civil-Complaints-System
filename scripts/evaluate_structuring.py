"""
평가 스크립트 - 구조화 평가

구조화된 데이터의 정확도를 평가한다.

Usage:
    python scripts/evaluate_structuring.py --gold data/annotations/gold.json
"""

import sys
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import evaluation_logger


FIELDS = ["observation", "result", "request", "context"]


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9가-힣_]+", (text or "").lower())


def _token_f1(pred_text: str, gold_text: str) -> float:
    pred_tokens = _tokenize(pred_text)
    gold_tokens = _tokenize(gold_text)

    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    gold_counts: Dict[str, int] = {}
    for token in gold_tokens:
        gold_counts[token] = gold_counts.get(token, 0) + 1

    overlap = 0
    for token in pred_tokens:
        if gold_counts.get(token, 0) > 0:
            overlap += 1
            gold_counts[token] -= 1

    precision = _safe_divide(overlap, len(pred_tokens))
    recall = _safe_divide(overlap, len(gold_tokens))
    return _safe_divide(2 * precision * recall, precision + recall)


def _extract_field_text(record: Dict[str, Any], field: str) -> str:
    value = record.get(field)
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _compute_field_metrics(gold_rows: List[Dict[str, Any]], pred_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    by_field: Dict[str, Dict[str, float]] = {}

    for field in FIELDS:
        tp = 0
        fp = 0
        fn = 0

        for gold in gold_rows:
            case_id = str(gold.get("case_id") or "").strip()
            if not case_id:
                continue

            pred = pred_map.get(case_id, {})
            gold_text = _extract_field_text(gold, field)
            pred_text = _extract_field_text(pred, field)

            matched = _token_f1(pred_text, gold_text) >= 0.7
            gold_exists = bool(gold_text)
            pred_exists = bool(pred_text)

            if pred_exists and matched:
                tp += 1
            elif pred_exists and not matched:
                fp += 1

            if gold_exists and not matched:
                fn += 1

        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        f1 = _safe_divide(2 * precision * recall, precision + recall)

        by_field[field] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    macro_f1 = round(
        sum(by_field[field]["f1"] for field in FIELDS) / len(FIELDS),
        4,
    )
    return {"fields": by_field, "macro_f1": macro_f1}


def _compute_quality_rates(pred_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    total = len(pred_rows)
    if total == 0:
        return {
            "schema_pass_rate": 0.0,
            "empty_field_rate": 0.0,
        }

    valid_count = 0
    empty_fields = 0
    total_fields = total * len(FIELDS)

    for row in pred_rows:
        validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
        if validation.get("is_valid") is True:
            valid_count += 1

        for field in FIELDS:
            if not _extract_field_text(row, field):
                empty_fields += 1

    return {
        "schema_pass_rate": round(_safe_divide(valid_count, total), 4),
        "empty_field_rate": round(_safe_divide(empty_fields, total_fields), 4),
    }


def _load_rows(file_path: str) -> List[Dict[str, Any]]:
    with Path(file_path).open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [row for row in payload["data"] if isinstance(row, dict)]
    raise ValueError("입력 파일은 객체 배열 또는 data 배열을 포함한 객체여야 합니다.")


def main(gold_file: str, pred_file: str, output_file: str):
    """메인 함수"""
    logger = evaluation_logger

    try:
        logger.info(f"구조화 평가 시작: gold={gold_file}, pred={pred_file}")

        gold_rows = _load_rows(gold_file)
        pred_rows = _load_rows(pred_file)
        pred_map = {
            str(row.get("case_id") or "").strip(): row
            for row in pred_rows
            if str(row.get("case_id") or "").strip()
        }

        field_metrics = _compute_field_metrics(gold_rows, pred_map)
        quality_rates = _compute_quality_rates(pred_rows)

        report = {
            "gold_count": len(gold_rows),
            "pred_count": len(pred_rows),
            "matched_case_count": sum(
                1 for row in gold_rows if str(row.get("case_id") or "").strip() in pred_map
            ),
            "metrics": field_metrics,
            "quality": quality_rates,
            "kpi": {
                "target_f1": 0.72,
                "target_schema_pass_rate": 0.95,
                "actual_f1": field_metrics["macro_f1"],
                "actual_schema_pass_rate": quality_rates["schema_pass_rate"],
                "f1_passed": field_metrics["macro_f1"] >= 0.72,
                "schema_passed": quality_rates["schema_pass_rate"] >= 0.95,
            },
        }

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"구조화 평가 완료: 결과 파일={output_file}")

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
    parser.add_argument(
        "--pred",
        type=str,
        required=True,
        help="예측 데이터 파일 경로",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/annotations/structuring_eval_result.json",
        help="평가 결과 출력 경로",
    )
    args = parser.parse_args()

    main(args.gold, args.pred, args.output)

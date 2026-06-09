"""responsible_unit 평가 스크립트.

평가 파일(JSONL)의 각 질의에 DepartmentAssigner.assign()을 실행하고,
Recall@K, MRR@K, NONE 케이스 무답률을 계산한다.

사용 예:
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.seed.jsonl
  python scripts/eval_responsible_unit.py --eval-file data/departments/eval/responsible_unit_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_EVAL_FILE = ROOT / "data" / "departments" / "eval" / "responsible_unit_eval.jsonl"
DEFAULT_MASTER_FILE = ROOT / "data" / "departments" / "busan_departments_master.json"
NONE_LABEL = "NONE"


@dataclass(frozen=True)
class EvalCase:
    """평가용 단일 민원 케이스."""

    query: str
    gold: List[str]
    case_id: str = ""
    note: str = ""

    @property
    def is_none(self) -> bool:
        return self.gold == [NONE_LABEL]


@dataclass(frozen=True)
class CaseResult:
    """단일 케이스 평가 결과."""

    case: EvalCase
    predictions: List[Dict[str, Any]]
    hit: bool
    reciprocal_rank: float
    abstained: bool

    @property
    def top_confidence(self) -> float:
        if not self.predictions:
            return 0.0
        try:
            return float(self.predictions[0].get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0


def load_department_names(master_file: Path) -> set[str]:
    """마스터 파일에서 실제 배정 가능한 부서명을 읽는다."""
    data = json.loads(master_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"마스터 파일 형식이 배열이 아닙니다: {master_file}")
    return {str(row.get("department", "")).strip() for row in data if row.get("department")}


def load_eval_cases(eval_file: Path, allowed_names: Optional[set[str]] = None) -> List[EvalCase]:
    """JSONL 평가셋을 읽고 최소 스키마와 gold 부서명을 검증한다."""
    cases: List[EvalCase] = []
    allowed_names = allowed_names or set()

    for line_no, raw in enumerate(eval_file.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{eval_file}:{line_no} JSON 파싱 실패: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{eval_file}:{line_no} 객체가 아닙니다.")

        query = str(row.get("query", "")).strip()
        gold_raw = row.get("gold", [])
        if not query:
            raise ValueError(f"{eval_file}:{line_no} query가 비어 있습니다.")
        if not isinstance(gold_raw, list) or not gold_raw:
            raise ValueError(f"{eval_file}:{line_no} gold는 비어 있지 않은 배열이어야 합니다.")

        gold = [str(x).strip() for x in gold_raw if str(x).strip()]
        if not gold:
            raise ValueError(f"{eval_file}:{line_no} gold가 비어 있습니다.")
        if NONE_LABEL in gold and gold != [NONE_LABEL]:
            raise ValueError(f"{eval_file}:{line_no} NONE은 단독 라벨로만 사용할 수 있습니다.")
        if allowed_names:
            invalid = [name for name in gold if name != NONE_LABEL and name not in allowed_names]
            if invalid:
                raise ValueError(f"{eval_file}:{line_no} 마스터에 없는 gold 부서: {invalid}")

        cases.append(EvalCase(
            query=query,
            gold=gold,
            case_id=str(row.get("id", "")).strip(),
            note=str(row.get("note", "")).strip(),
        ))
    if not cases:
        raise ValueError(f"평가 케이스가 없습니다: {eval_file}")
    return cases


def evaluate_predictions(
    cases: Sequence[EvalCase],
    predict: Callable[[str], List[Dict[str, Any]]],
    *,
    top_k: int = 3,
    none_confidence_threshold: float = 0.4,
) -> Dict[str, Any]:
    """예측 함수를 주입받아 평가 지표를 계산한다.

    NONE 케이스는 정답 부서가 마스터 풀에 없다는 뜻이므로 Recall/MRR 계산에서 제외하고,
    후보가 없거나 top confidence가 낮으면 abstain으로 집계한다.
    """
    if top_k < 1:
        raise ValueError("top_k는 1 이상이어야 합니다.")

    results: List[CaseResult] = []
    normal_count = 0
    hit_count = 0
    reciprocal_sum = 0.0
    none_count = 0
    abstain_count = 0

    for case in cases:
        predictions = predict(case.query) or []
        ranked_names = [str(p.get("name", "")).strip() for p in predictions[:top_k]]
        top_confidence = 0.0
        if predictions:
            try:
                top_confidence = float(predictions[0].get("confidence", 0.0))
            except (TypeError, ValueError):
                top_confidence = 0.0
        abstained = (not predictions) or top_confidence < none_confidence_threshold

        if case.is_none:
            none_count += 1
            if abstained:
                abstain_count += 1
            results.append(CaseResult(case, predictions, False, 0.0, abstained))
            continue

        normal_count += 1
        rr = 0.0
        for idx, name in enumerate(ranked_names, start=1):
            if name in case.gold:
                rr = 1.0 / idx
                break
        hit = rr > 0
        if hit:
            hit_count += 1
            reciprocal_sum += rr
        results.append(CaseResult(case, predictions, hit, rr, abstained))

    recall = hit_count / normal_count if normal_count else 0.0
    mrr = reciprocal_sum / normal_count if normal_count else 0.0
    none_abstention_rate = abstain_count / none_count if none_count else None

    return {
        "top_k": top_k,
        "total_cases": len(cases),
        "labeled_cases": normal_count,
        "none_cases": none_count,
        "recall_at_k": round(recall, 6),
        "mrr_at_k": round(mrr, 6),
        "none_confidence_threshold": none_confidence_threshold,
        "none_abstention_rate": None if none_abstention_rate is None else round(none_abstention_rate, 6),
        "case_results": results,
    }


def _truncate(text: str, limit: int = 64) -> str:
    """CLI 표 출력을 위한 짧은 문자열."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_names(predictions: Sequence[Dict[str, Any]], top_k: int) -> str:
    """예측 부서명과 confidence를 한 줄로 표시한다."""
    parts = []
    for pred in predictions[:top_k]:
        name = str(pred.get("name", "")).strip()
        conf = pred.get("confidence", 0.0)
        parts.append(f"{name}({conf})")
    return ", ".join(parts) if parts else "-"


def print_text_report(metrics: Dict[str, Any]) -> None:
    """평가 결과를 사람이 읽는 텍스트 표로 출력한다."""
    print("responsible_unit evaluation")
    print(f"- total: {metrics['total_cases']}")
    print(f"- labeled: {metrics['labeled_cases']}")
    print(f"- NONE: {metrics['none_cases']}")
    print(f"- Recall@{metrics['top_k']}: {metrics['recall_at_k']:.4f}")
    print(f"- MRR@{metrics['top_k']}: {metrics['mrr_at_k']:.4f}")
    if metrics["none_abstention_rate"] is None:
        print("- NONE abstention: n/a")
    else:
        print(
            f"- NONE abstention: {metrics['none_abstention_rate']:.4f} "
            f"(threshold={metrics['none_confidence_threshold']})"
        )

    print()
    header = f"{'id':<12} {'hit':<5} {'rr':<6} {'gold':<24} {'predictions':<44} query"
    print(header)
    print("-" * len(header))
    for result in metrics["case_results"]:
        case = result.case
        hit = "NONE" if case.is_none else ("Y" if result.hit else "N")
        rr = f"{result.reciprocal_rank:.3f}"
        case_id = case.case_id or "-"
        gold = ",".join(case.gold)
        preds = _format_names(result.predictions, metrics["top_k"])
        print(
            f"{_truncate(case_id, 12):<12} {hit:<5} {rr:<6} "
            f"{_truncate(gold, 24):<24} {_truncate(preds, 44):<44} {_truncate(case.query)}"
        )


def serializable_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """JSON 저장/출력을 위해 dataclass 결과를 일반 dict로 변환한다."""
    out = dict(metrics)
    out["case_results"] = [
        {
            "id": result.case.case_id,
            "query": result.case.query,
            "gold": result.case.gold,
            "predictions": result.predictions,
            "hit": result.hit,
            "reciprocal_rank": result.reciprocal_rank,
            "abstained": result.abstained,
            "top_confidence": result.top_confidence,
        }
        for result in metrics["case_results"]
    ]
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI 인자를 정의한다."""
    parser = argparse.ArgumentParser(description="responsible_unit 후보 검색 평가")
    parser.add_argument("--eval-file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--master-file", type=Path, default=DEFAULT_MASTER_FILE)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--top-k-tasks", type=int, default=20)
    parser.add_argument("--use-reranker", action="store_true", help="CrossEncoder task 리랭킹을 켭니다.")
    parser.add_argument("--none-confidence-threshold", type=float, default=0.4)
    parser.add_argument("--json", action="store_true", help="텍스트 표 대신 JSON을 출력합니다.")
    parser.add_argument("--output-json", type=Path, default=None, help="평가 결과 JSON 저장 경로")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI 진입점."""
    args = build_arg_parser().parse_args(argv)
    allowed_names = load_department_names(args.master_file)
    cases = load_eval_cases(args.eval_file, allowed_names=allowed_names)

    from app.structuring.department_assigner import get_department_assigner

    assigner = get_department_assigner()

    def predict(query: str) -> List[Dict[str, Any]]:
        return assigner.assign(
            query,
            top_k_tasks=args.top_k_tasks,
            top_n_units=args.top_k,
            min_confidence=0.0,
            use_llm=False,
            use_reranker=args.use_reranker,
        )

    metrics = evaluate_predictions(
        cases,
        predict,
        top_k=args.top_k,
        none_confidence_threshold=args.none_confidence_threshold,
    )
    metrics["run_config"] = {
        "top_k_tasks": args.top_k_tasks,
        "use_reranker": args.use_reranker,
        "reranker_model": getattr(assigner, "reranker_model_name", ""),
        "reranker_used": bool(getattr(assigner, "_reranker_used", False)),
        "reranker_unavailable": bool(getattr(assigner, "_reranker_unavailable", False)),
    }
    payload = serializable_metrics(metrics)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text_report(metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

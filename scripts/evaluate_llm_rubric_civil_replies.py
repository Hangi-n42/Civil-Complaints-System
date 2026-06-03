"""LLM-Rubric inspired evaluator for generated civil-affairs replies.

This script implements a deterministic proxy of the LLM-Rubric questionnaire.
It does not train the calibration network from the paper; instead, it produces
Q0-Q8 rubric scores that can be used immediately for benchmark diagnostics.

Example:
    python scripts/evaluate_llm_rubric_civil_replies.py \
      --answers logs/evaluation/week6/.../parsed_answers.jsonl \
      --cases VS_지방행정기관/rand_test_50.json \
      --output-dir logs/evaluation/week6/rubric_eval
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]


RUBRIC_DESCRIPTIONS: Dict[str, str] = {
    "Q0": "종합 만족도: 민원인이 회신을 읽고 전반적으로 만족할 가능성",
    "Q1": "대화의 질: 공공기관 회신으로서 자연스러운 어조와 형식",
    "Q2": "근거 충분성: 제공된 검색 근거로 민원 해결 방향을 설명할 수 있는 정도",
    "Q3": "인용 포함: 답변의 주요 주장에 출처 토큰이 붙어 있는 정도",
    "Q4": "인용 정확성: 인용이 검색 컨텍스트와 매칭되는 정도",
    "Q5": "최적 출처성: 출력이 유효한 근거를 우선 사용한 정도",
    "Q6": "중복 없음: 반복, 과잉 사양, 디버그 문자열이 없는 정도",
    "Q7": "간결성: 민원 회신으로 적절한 길이와 밀도",
    "Q8": "효율성: 단일 회신에서 민원 요지, 검토, 후속 안내가 적절히 끝나는 정도",
}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _read_cases(path: Path | None) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    if not isinstance(raw, list):
        raise ValueError("cases file must be a JSON list")
    cases: Dict[str, Dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or item.get("source_id") or item.get("complaint_id") or "").strip()
        if case_id:
            cases[case_id] = item
    return cases


def _clip_score(value: float) -> int:
    return max(1, min(4, int(round(value))))


def _sentence_count(text: str) -> int:
    parts = re.split(r"(?<=[.!?。！？다요음임함됨됨니다])\s+|\n+", text or "")
    return len([part for part in parts if part.strip()])


def _source_token_count(text: str) -> int:
    return len(re.findall(r"\[\[출처\s*\d+\]\]", text or ""))


def _has_real_reply_specificity(answer: str) -> bool:
    """실제 지자체 답변 표본의 최고점 특징: 구체 담당/일정/법령/불가 사유 중 일부가 존재."""
    text = answer or ""
    signals = [
        bool(re.search(r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}|'\d{2}\.\s*\d{1,2}\.\s*\d{1,2}|\d{1,2}월|\d{1,2}일", text)),
        bool(re.search(r"「[^」]+」|법률|조례|규칙|규정|지침|예산|계획", text)),
        bool(re.search(r"주무관|담당자|담당부서|[\w가-힣]+과|[\w가-힣]+팀", text)),
        bool(re.search(r"어려움|어렵|불가|양해|검토\s*중|추후|순차|현장\s*확인|관계\s*부서", text)),
        bool(re.search(r"가\.\s|나\.\s|다\.\s|○|- ", text)),
    ]
    return sum(signals) >= 2


def _generic_reply_penalty(answer: str) -> tuple[int, List[str]]:
    generic_phrases = [
        "위 내용을 바탕으로 담당부서에서는 현장 여건, 관련 기준, 유사 처리 사례를 확인한 뒤",
        "필요한 조치 가능 여부를 판단할 수 있습니다",
        "접수 내용과 관련 자료를 확인한 뒤",
        "현장 여건, 행정 처리 기준, 조치 가능 범위를 종합적으로 검토하겠습니다",
        "확인 결과에 따라 필요한 안내 또는 후속 조치가 이루어질 수 있습니다",
    ]
    hits = [phrase for phrase in generic_phrases if phrase in (answer or "")]
    if len(hits) >= 2:
        return 2, ["템플릿성 일반 문구가 과다함"]
    if hits:
        return 1, ["템플릿성 일반 문구 포함"]
    return 0, []


def _has_debug_noise(text: str) -> bool:
    return bool(
        re.search(
            r"chunk_id=|case_id=|score=|CASE-\d+__chunk-\d+|```|^\s*#{1,6}\s|\*\*",
            text or "",
            flags=re.IGNORECASE | re.MULTILINE,
        )
    )


def _repetition_ratio(text: str) -> float:
    sentences = [s.strip() for s in re.split(r"[.!?\n]+", text or "") if len(s.strip()) >= 8]
    if not sentences:
        return 0.0
    counts = Counter(sentences)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / max(len(sentences), 1)


def _answer_from_row(row: Dict[str, Any], answer_field: str) -> str:
    for key in (answer_field, "parsed_answer_repaired", "parsed_answer", "parsed_answer_strict", "answer"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _score_q1_naturalness(answer: str) -> tuple[int, List[str]]:
    reasons: List[str] = []
    score = 4
    if not re.search(r"(^|\n)\s*1\.", answer):
        score -= 1
        reasons.append("번호 단락 회신 형식이 약함")
    if not any(token in answer for token in ("귀하", "민원", "검토", "답변", "감사합니다")):
        score -= 1
        reasons.append("공공기관 회신 어휘가 부족함")
    if _has_debug_noise(answer):
        score -= 2
        reasons.append("Markdown 또는 검색 메타데이터가 노출됨")
    if len(answer.strip()) < 120:
        score -= 1
        reasons.append("회신 본문이 지나치게 짧음")
    penalty, penalty_reasons = _generic_reply_penalty(answer)
    if penalty:
        score -= penalty
        reasons.extend(penalty_reasons)
    return max(1, score), reasons


def _score_q2_source_adequacy(row: Dict[str, Any], answer: str) -> tuple[int, List[str]]:
    strict = float(row.get("citation_match_rate_strict") or 0.0)
    repaired = float(row.get("citation_match_rate_repaired") or row.get("citation_match_rate") or 0.0)
    count = int(row.get("citations_count_repaired") or row.get("citations_count") or 0)
    specific = _has_real_reply_specificity(answer)
    if strict >= 0.8 and count > 0 and specific:
        return 4, ["strict 기준 근거 매칭이 충분하고 실제 답변 수준의 구체성이 있음"]
    if strict >= 0.8 and count > 0:
        return 3, ["strict 기준 근거 매칭은 충분하지만 구체성이 부족함"]
    if repaired >= 0.8 and count > 0:
        return 2, ["보정 후 근거 매칭은 충분하지만 strict 근거 또는 구체성이 약함"]
    if count > 0:
        return 1, ["근거는 있으나 컨텍스트 매칭률이 낮음"]
    return 1, ["사용 가능한 근거가 없음"]


def _score_q3_citation_coverage(answer: str, row: Dict[str, Any]) -> tuple[int, List[str]]:
    tokens = _source_token_count(answer)
    repaired_count = int(row.get("citations_count_repaired") or row.get("citations_count") or 0)
    if repaired_count <= 0:
        return 1, ["citations가 없음"]
    ratio = tokens / max(repaired_count, 1)
    if ratio >= 1.0:
        return 4, ["출처 토큰 수가 citations 수를 충족함"]
    if ratio >= 0.5:
        return 3, ["주요 출처 토큰은 있으나 일부 부족함"]
    if tokens > 0:
        return 2, ["출처 토큰이 일부만 있음"]
    return 1, ["답변 본문에 출처 토큰이 없음"]


def _score_by_rate(rate: float, label: str) -> tuple[int, List[str]]:
    if rate >= 0.95:
        return 4, [f"{label}={rate:.2f}"]
    if rate >= 0.5:
        return 3, [f"{label}={rate:.2f}"]
    if rate > 0:
        return 2, [f"{label}={rate:.2f}"]
    return 1, [f"{label}=0.00"]


def _score_q4_citation_accuracy(strict_rate: float, repaired_rate: float) -> tuple[int, List[str]]:
    if strict_rate >= 0.95:
        return 4, [f"strict citation_match_rate={strict_rate:.2f}"]
    if strict_rate >= 0.5:
        return 3, [f"strict citation_match_rate={strict_rate:.2f}"]
    if repaired_rate >= 0.95:
        return 2, [f"strict citation은 약하지만 repaired citation_match_rate={repaired_rate:.2f}"]
    if repaired_rate > 0:
        return 2, [f"repaired citation_match_rate={repaired_rate:.2f}"]
    return 1, ["citation_match_rate=0.00"]


def _score_q6_redundancy(answer: str) -> tuple[int, List[str]]:
    ratio = _repetition_ratio(answer)
    reasons: List[str] = []
    score = 4
    if ratio > 0.15:
        score -= 2
        reasons.append(f"반복 문장 비율이 높음({ratio:.2f})")
    elif ratio > 0:
        score -= 1
        reasons.append(f"일부 반복 감지({ratio:.2f})")
    if _has_debug_noise(answer):
        score -= 2
        reasons.append("디버그/Markdown 노이즈 감지")
    if answer.count("[[출처") > 4:
        score -= 1
        reasons.append("출처 토큰이 과도하게 반복됨")
    penalty, penalty_reasons = _generic_reply_penalty(answer)
    if penalty:
        score -= penalty
        reasons.extend(penalty_reasons)
    return max(1, score), reasons


def _score_q7_conciseness(answer: str) -> tuple[int, List[str]]:
    length = len(answer)
    sentences = _sentence_count(answer)
    # VS_지방행정기관 실제 답변 표본 기준: 중앙값 약 460자, IQR 약 360~590자.
    if 360 <= length <= 650 and 5 <= sentences <= 14:
        return 4, [f"실제 답변 표본에 가까운 길이({length}자, {sentences}문장)"]
    if 250 <= length < 360 or 650 < length <= 900:
        return 3, [f"약간 짧거나 김({length}자)"]
    if 120 <= length < 250 or 900 < length <= 1300:
        return 2, [f"회신 길이 부적정({length}자)"]
    return 1, [f"매우 짧거나 과도하게 김({length}자)"]


def _score_q8_efficiency(answer: str) -> tuple[int, List[str]]:
    has_summary = "민원 내용" in answer or "질의내용" in answer or "요청" in answer
    has_review = "검토" in answer or "의견" in answer or "알려드립니다" in answer
    has_followup = "문의" in answer or "추가 설명" in answer or "담당부서" in answer
    points = sum([has_summary, has_review, has_followup])
    specific = _has_real_reply_specificity(answer)
    penalty, penalty_reasons = _generic_reply_penalty(answer)
    if points == 3 and specific and not penalty:
        return 4, ["요지-검토-후속 안내가 모두 포함됨"]
    if points == 2:
        return 3, ["핵심 회신 요소 중 하나가 부족함"]
    if points == 3:
        reasons = ["요지-검토-후속 안내는 있으나 실제 답변 수준의 구체성이 부족함"]
        reasons.extend(penalty_reasons)
        return 3, reasons
    if points == 1:
        return 2, ["회신 흐름이 부분적으로만 구성됨"]
    return 1, ["민원 회신 흐름이 거의 없음"]


def evaluate_row(row: Dict[str, Any], case: Dict[str, Any], answer_field: str) -> Dict[str, Any]:
    answer = _answer_from_row(row, answer_field)

    q1, q1_reasons = _score_q1_naturalness(answer)
    q2, q2_reasons = _score_q2_source_adequacy(row, answer)
    q3, q3_reasons = _score_q3_citation_coverage(answer, row)
    strict_rate = float(row.get("citation_match_rate_strict") or 0.0)
    repaired_rate = float(row.get("citation_match_rate_repaired") or row.get("citation_match_rate") or 0.0)
    q4, q4_reasons = _score_q4_citation_accuracy(strict_rate, repaired_rate)
    q5, q5_reasons = _score_by_rate(strict_rate if strict_rate > 0 else repaired_rate * 0.75, "best_source_proxy")
    q6, q6_reasons = _score_q6_redundancy(answer)
    q7, q7_reasons = _score_q7_conciseness(answer)
    q8, q8_reasons = _score_q8_efficiency(answer)

    weighted = (
        0.16 * q1
        + 0.10 * q2
        + 0.14 * q3
        + 0.16 * q4
        + 0.10 * q5
        + 0.12 * q6
        + 0.12 * q7
        + 0.10 * q8
    )
    q0 = _clip_score(weighted)

    rubric = {
        "Q0": {"score": q0, "label": RUBRIC_DESCRIPTIONS["Q0"], "reasons": [f"weighted_proxy={weighted:.2f}"]},
        "Q1": {"score": q1, "label": RUBRIC_DESCRIPTIONS["Q1"], "reasons": q1_reasons},
        "Q2": {"score": q2, "label": RUBRIC_DESCRIPTIONS["Q2"], "reasons": q2_reasons},
        "Q3": {"score": q3, "label": RUBRIC_DESCRIPTIONS["Q3"], "reasons": q3_reasons},
        "Q4": {"score": q4, "label": RUBRIC_DESCRIPTIONS["Q4"], "reasons": q4_reasons},
        "Q5": {"score": q5, "label": RUBRIC_DESCRIPTIONS["Q5"], "reasons": q5_reasons},
        "Q6": {"score": q6, "label": RUBRIC_DESCRIPTIONS["Q6"], "reasons": q6_reasons},
        "Q7": {"score": q7, "label": RUBRIC_DESCRIPTIONS["Q7"], "reasons": q7_reasons},
        "Q8": {"score": q8, "label": RUBRIC_DESCRIPTIONS["Q8"], "reasons": q8_reasons},
    }

    return {
        "case_id": str(row.get("case_id") or ""),
        "model_id": row.get("model_id"),
        "model_name": row.get("model_name"),
        "source": case.get("source"),
        "category": case.get("category") or case.get("consulting_category"),
        "answer_len": len(answer),
        "source_token_count": _source_token_count(answer),
        "citation_match_rate_strict": strict_rate,
        "citation_match_rate_repaired": repaired_rate,
        "rubric": rubric,
    }


def _average(values: Iterable[float]) -> float:
    vals = list(values)
    return statistics.fmean(vals) if vals else 0.0


def build_report(scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_q: Dict[str, float] = {}
    for qid in RUBRIC_DESCRIPTIONS:
        by_q[qid] = round(_average(row["rubric"][qid]["score"] for row in scores), 4)

    q0_values = [row["rubric"]["Q0"]["score"] for row in scores]
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for row in scores:
        categories.setdefault(str(row.get("category") or "unknown"), []).append(row)

    return {
        "method": "llm_rubric_proxy_civil_replies",
        "note": "Deterministic proxy of LLM-Rubric Q0-Q8; no learned calibration network is applied.",
        "count": len(scores),
        "average_scores": by_q,
        "q0_distribution": dict(sorted(Counter(q0_values).items())),
        "category_summary": {
            category: {
                "count": len(rows),
                "Q0": round(_average(row["rubric"]["Q0"]["score"] for row in rows), 4),
                "Q1": round(_average(row["rubric"]["Q1"]["score"] for row in rows), 4),
                "Q4": round(_average(row["rubric"]["Q4"]["score"] for row in rows), 4),
                "Q7": round(_average(row["rubric"]["Q7"]["score"] for row in rows), 4),
            }
            for category, rows in sorted(categories.items())
        },
    }


def write_summary_md(report: Dict[str, Any], output_path: Path) -> None:
    lines = [
        "# LLM-Rubric Proxy Evaluation Summary",
        "",
        f"- method: `{report['method']}`",
        f"- count: {report['count']}",
        "- scale: 1(low) to 4(high)",
        "",
        "## Average Scores",
        "",
        "| question | score | meaning |",
        "| --- | ---: | --- |",
    ]
    for qid, score in report["average_scores"].items():
        lines.append(f"| {qid} | {score} | {RUBRIC_DESCRIPTIONS[qid]} |")

    lines.extend(["", "## Category Summary", "", "| category | count | Q0 | Q1 | Q4 | Q7 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for category, row in report["category_summary"].items():
        lines.append(f"| {category} | {row['count']} | {row['Q0']} | {row['Q1']} | {row['Q4']} | {row['Q7']} |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate generated civil-affairs replies with an LLM-Rubric proxy.")
    parser.add_argument("--answers", required=True, help="parsed_answers.jsonl path")
    parser.add_argument("--cases", default=None, help="benchmark cases JSON path")
    parser.add_argument("--output-dir", required=True, help="directory for rubric_scores.jsonl/report/summary")
    parser.add_argument("--answer-field", default="parsed_answer_repaired")
    args = parser.parse_args()

    answers_path = (PROJECT_ROOT / args.answers).resolve()
    cases_path = (PROJECT_ROOT / args.cases).resolve() if args.cases else None
    output_dir = (PROJECT_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = _read_cases(cases_path)
    rows = _read_jsonl(answers_path)
    scores = [
        evaluate_row(row, cases.get(str(row.get("case_id") or ""), {}), args.answer_field)
        for row in rows
    ]
    report = build_report(scores)

    score_path = output_dir / "rubric_scores.jsonl"
    with score_path.open("w", encoding="utf-8") as handle:
        for row in scores:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report_path = output_dir / "rubric_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_path = output_dir / "rubric_summary.md"
    write_summary_md(report, summary_path)

    print(f"[DONE] scores: {score_path}")
    print(f"[DONE] report: {report_path}")
    print(f"[DONE] summary: {summary_path}")


if __name__ == "__main__":
    main()

"""중복 민원 병합 100쌍 라벨 평가셋을 평가한다."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.complaint_intelligence.duplicate_merger.scoring import score_duplicate_pair
from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeConflict, DuplicateMergeService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent


DATASET_PATH = Path("data/evaluation/duplicate_merge_labeled_pairs.json")
JSON_REPORT_PATH = Path("reports/duplicate_merge_labeled_eval_report.json")
MD_REPORT_PATH = Path("reports/duplicate_merge_labeled_eval_report.md")
BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)
PHONE_RE = re.compile(r"010-\d{4}-\d{4}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@example\.com")
UNIT_ADDRESS_RE = re.compile(r"\d+동\s*\d+호")


def build_synthetic_dataset() -> list[dict[str, Any]]:
    """운영 리스크 축별로 25쌍씩, 총 100쌍의 합성 라벨 평가셋을 만든다."""

    pairs: list[dict[str, Any]] = []
    pairs.extend(_true_duplicate_pairs())
    pairs.extend(_same_keyword_different_event_pairs())
    pairs.extend(_same_event_different_request_pairs())
    pairs.extend(_pii_risk_pairs())
    if len(pairs) != 100:
        raise ValueError(f"평가셋은 100쌍이어야 합니다: {len(pairs)}")
    return pairs


def load_dataset(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("duplicate merge 평가셋은 list JSON이어야 합니다.")
    return data


def write_dataset(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    pairs = build_synthetic_dataset()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pairs


def evaluate_dataset(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """pair 단위 예측 결과와 운영 지표를 계산한다."""

    started = time.perf_counter()
    results = []
    counts = Counter(pair["category"] for pair in pairs)
    risk_flag_counts: Counter[str] = Counter()
    candidate_tp = candidate_fp = candidate_tn = candidate_fn = 0
    blocker_expected = blocker_hit = 0
    risk_expected = risk_hit = 0
    pii_payloads = pii_leaks = 0
    category_summary: dict[str, Counter] = defaultdict(Counter)

    for pair in pairs:
        left = ComplaintIntelligenceEvent.model_validate(pair["left_event"])
        right = ComplaintIntelligenceEvent.model_validate(pair["right_event"])
        score_result = score_duplicate_pair(left, right)
        service = DuplicateMergeService()
        groups = service.run_analysis([left, right])
        group = groups[0] if groups else None
        predicted_candidate = group is not None
        expected_candidate = bool(pair["expected_candidate"])

        if predicted_candidate and expected_candidate:
            candidate_tp += 1
            category_summary[pair["category"]]["tp"] += 1
        elif predicted_candidate and not expected_candidate:
            candidate_fp += 1
            category_summary[pair["category"]]["fp"] += 1
        elif not predicted_candidate and not expected_candidate:
            candidate_tn += 1
            category_summary[pair["category"]]["tn"] += 1
        else:
            candidate_fn += 1
            category_summary[pair["category"]]["fn"] += 1

        risk_flags = {flag.code for flag in group.risk_flags} if group else set()
        risk_flag_counts.update(risk_flags)
        allowed_actions = set(group.allowed_actions) if group else set()
        confirm_allowed = "confirm" in allowed_actions
        expected_flags = set(pair.get("expected_risk_flags") or [])
        if expected_candidate and not bool(pair["expected_confirm_allowed"]):
            blocker_expected += 1
            if predicted_candidate and not confirm_allowed:
                blocker_hit += 1
        if expected_flags:
            risk_expected += 1
            if expected_flags <= risk_flags or (not expected_candidate and not predicted_candidate):
                risk_hit += 1

        pii_leaked = False
        if pair["category"] == "PII risk" and predicted_candidate and confirm_allowed and group is not None:
            pii_payloads += 1
            confirmed = service.confirm_group(group.merge_id)
            payload = service.build_draft_reply_payload(confirmed.merge_id)
            serialized = payload.model_dump_json()
            pii_leaked = _has_raw_pii_leak(pair, serialized)
            if pii_leaked:
                pii_leaks += 1
        elif pair["category"] == "PII risk" and predicted_candidate and group is not None:
            pii_payloads += 1
            try:
                payload = service.build_draft_reply_payload(group.merge_id)
                pii_leaked = _has_raw_pii_leak(pair, payload.model_dump_json())
            except DuplicateMergeConflict:
                pii_leaked = False

        results.append(
            {
                "pair_id": pair["pair_id"],
                "category": pair["category"],
                "expected_candidate": expected_candidate,
                "predicted_candidate": predicted_candidate,
                "expected_confirm_allowed": bool(pair["expected_confirm_allowed"]),
                "predicted_confirm_allowed": confirm_allowed,
                "expected_risk_flags": sorted(expected_flags),
                "predicted_risk_flags": sorted(risk_flags),
                "expected_location_state": pair["expected_location_state"],
                "predicted_location_state": group.location_state if group else score_result.location_state,
                "expected_request_types": pair["expected_request_types"],
                "predicted_request_types": score_result.request_types,
                "score": score_result.score,
                "pii_leaked": pii_leaked,
            }
        )

    precision = _safe_div(candidate_tp, candidate_tp + candidate_fp)
    recall = _safe_div(candidate_tp, candidate_tp + candidate_fn)
    false_positive_rate = _safe_div(candidate_fp, candidate_fp + candidate_tn)
    blocker_recall = _safe_div(blocker_hit, blocker_expected)
    risk_flag_hit_rate = _safe_div(risk_hit, risk_expected)
    pii_leak_rate = _safe_div(pii_leaks, pii_payloads)
    elapsed_ms = (time.perf_counter() - started) * 1000
    problem_results = _problem_results(results)
    metrics = {
        "total_pairs": len(pairs),
        "category_counts": dict(sorted(counts.items())),
        "candidate_confusion": {
            "tp": candidate_tp,
            "fp": candidate_fp,
            "tn": candidate_tn,
            "fn": candidate_fn,
        },
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "blocker_recall": round(blocker_recall, 4),
        "risk_flag_hit_rate": round(risk_flag_hit_rate, 4),
        "pii_leak_rate": round(pii_leak_rate, 4),
        "pii_payloads_evaluated": pii_payloads,
        "elapsed_ms": round(elapsed_ms, 2),
        "average_ms_per_pair": round(_safe_div(elapsed_ms, len(pairs)), 4),
        "estimated_score_calls": len(pairs) * 2,
        "problem_result_count": len(problem_results),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "category_summary": {key: dict(value) for key, value in sorted(category_summary.items())},
    }
    return {"metrics": metrics, "diagnostics": {"problem_examples": problem_results[:10]}, "results": results}


def write_reports(evaluation: dict[str, Any]) -> None:
    JSON_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_REPORT_PATH.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MD_REPORT_PATH.write_text(_markdown_report(evaluation), encoding="utf-8")


def _true_duplicate_pairs() -> list[dict[str, Any]]:
    templates = [
        ("apartment-noise", "행복아파트", "환경관리과", "생활불편", "야간 공사 소음 보수 요청", "facility_improvement", ["행복아파트", "정문", "소음"]),
        ("road-pothole", "중앙로12길", "도로관리과", "도로", "도로 파임 긴급 점검 요청", "safety_action", ["중앙로12길", "포트홀"]),
        ("trash-dump", "새빛공원", "청소행정과", "환경", "무단투기 단속 요청", "enforcement", ["새빛공원", "무단투기"]),
        ("streetlight", "푸른초등학교", "도로조명과", "시설", "가로등 교체 요청", "facility_improvement", ["푸른초등학교", "가로등"]),
        ("drainage", "한강대로5길", "하수관리과", "시설", "배수로 정비 요청", "facility_improvement", ["한강대로5길", "배수로"]),
    ]
    pairs = []
    for template_index, template in enumerate(templates):
        slug, place, department, civil_category, request, request_type, entities = template
        for offset in range(5):
            index = template_index * 5 + offset + 1
            left = _event(
                f"td-{index:03d}-a",
                place,
                department,
                civil_category,
                f"{place} 주변에서 같은 문제가 반복됩니다.",
                request,
                entities,
                minutes=offset * 3,
            )
            right = _event(
                f"td-{index:03d}-b",
                place,
                department,
                civil_category,
                f"{place} 인근 주민들이 같은 불편을 다시 신고했습니다.",
                request,
                entities + [f"{place} 인근"],
                minutes=offset * 3 + 1,
            )
            pairs.append(
                _pair(
                    f"TD-{index:03d}",
                    "true duplicate",
                    left,
                    right,
                    True,
                    True,
                    [],
                    "exact",
                    {left["id"]: request_type, right["id"]: request_type},
                    f"{slug} 동일 장소 동일 요청 반복 접수",
                )
            )
    return pairs


def _same_keyword_different_event_pairs() -> list[dict[str, Any]]:
    places = [
        ("중구청 앞", "중구문화센터 앞"),
        ("남산공원 북문", "남산공원 남문"),
        ("새빛아파트", "푸른아파트"),
        ("중앙로12길", "중앙로88길"),
        ("연희초등학교", "연희중학교"),
    ]
    pairs = []
    for group_index, (left_place, right_place) in enumerate(places):
        for offset in range(5):
            index = group_index * 5 + offset + 1
            request = "공사 소음 보수 요청"
            left = _event(
                f"sk-{index:03d}-a",
                "중구",
                "환경관리과",
                "생활불편",
                f"{left_place} 공사장에서 소음이 반복됩니다.",
                request,
                [left_place, "소음"],
                minutes=offset,
            )
            right = _event(
                f"sk-{index:03d}-b",
                "중구",
                "환경관리과",
                "생활불편",
                f"{right_place} 공사장에서 소음이 반복됩니다.",
                request,
                [right_place, "소음"],
                minutes=offset + 1,
            )
            pairs.append(
                _pair(
                    f"SK-{index:03d}",
                    "same keyword different event",
                    left,
                    right,
                    False,
                    False,
                    ["LOCATION_MISMATCH"],
                    "conflict",
                    {left["id"]: "facility_improvement", right["id"]: "facility_improvement"},
                    "같은 키워드지만 세부 장소가 다른 사건",
                )
            )
    return pairs


def _same_event_different_request_pairs() -> list[dict[str, Any]]:
    templates = [
        ("불법 주정차 단속 요청", "불법 주정차 차량으로 인한 피해 보상 요청", "enforcement", "compensation", ["REQUEST_TYPE_MISMATCH", "LEGAL_RIGHTS_OR_DEADLINE_RISK"]),
        ("도로 침하 긴급 안전 점검 요청", "도로 침하 처리 절차 문의", "safety_action", "inquiry", ["SAFETY_AND_INCONVENIENCE_MIXED", "REQUEST_TYPE_MISMATCH"]),
        ("가로등 교체 요청", "가로등 사고 피해 보상 요청", "facility_improvement", "compensation", ["REQUEST_TYPE_MISMATCH", "LEGAL_RIGHTS_OR_DEADLINE_RISK"]),
        ("무단투기 단속 요청", "무단투기 처리 절차 안내 요청", "enforcement", "guidance", ["REQUEST_TYPE_MISMATCH"]),
        ("놀이터 시설 보수 요청", "놀이터 안전사고 피해 보상 요청", "facility_improvement", "compensation", ["REQUEST_TYPE_MISMATCH", "LEGAL_RIGHTS_OR_DEADLINE_RISK"]),
    ]
    places = ["연희초등학교", "중앙로12길", "푸른공원", "새빛시장", "행복아파트"]
    pairs = []
    for template_index, template in enumerate(templates):
        left_request, right_request, left_type, right_type, expected_flags = template
        place = places[template_index]
        for offset in range(5):
            index = template_index * 5 + offset + 1
            left = _event(
                f"sr-{index:03d}-a",
                place,
                "민원관리과",
                "복합민원",
                f"{place}에서 같은 사건이 반복 접수되었습니다.",
                left_request,
                [place, "반복민원"],
                minutes=offset,
            )
            right = _event(
                f"sr-{index:03d}-b",
                place,
                "민원관리과",
                "복합민원",
                f"{place}의 같은 사건에 대해 다른 요구가 접수되었습니다.",
                right_request,
                [place, "반복민원"],
                minutes=offset + 1,
            )
            expected_confirm = "LEGAL_RIGHTS_OR_DEADLINE_RISK" not in expected_flags and "SAFETY_AND_INCONVENIENCE_MIXED" not in expected_flags
            pairs.append(
                _pair(
                    f"SR-{index:03d}",
                    "same event different request",
                    left,
                    right,
                    True,
                    expected_confirm,
                    expected_flags,
                    "exact",
                    {left["id"]: left_type, right["id"]: right_type},
                    "동일 사건 가능성은 있으나 요청 유형이 다름",
                )
            )
    return pairs


def _pii_risk_pairs() -> list[dict[str, Any]]:
    places = ["한빛아파트", "새움빌딩", "푸른공원", "중앙로12길", "연희초등학교"]
    pairs = []
    for group_index, place in enumerate(places):
        for offset in range(5):
            index = group_index * 5 + offset + 1
            phone = f"010-1234-{5600 + index:04d}"
            email = f"citizen{index:03d}@example.com"
            address = f"서울로 123 {100 + offset}동 {200 + offset}호"
            request = "시설 보수 요청"
            left = _event(
                f"pii-{index:03d}-a",
                place,
                "시설관리과",
                "시설",
                f"{place} 시설 파손이 반복됩니다. {phone} 연락 요청",
                request,
                [place, "시설파손", address],
                body=f"{address} 앞 시설 파손 신고입니다. 연락처 {phone}, 이메일 {email}",
                minutes=offset,
            )
            right = _event(
                f"pii-{index:03d}-b",
                place,
                "시설관리과",
                "시설",
                f"{place} 같은 위치 시설 파손 신고입니다. {email}로 회신 요청",
                request,
                [place, "시설파손", address],
                body=f"{address} 주변 시설 파손 반복 민원입니다. {phone}",
                minutes=offset + 1,
            )
            pairs.append(
                _pair(
                    f"PII-{index:03d}",
                    "PII risk",
                    left,
                    right,
                    True,
                    True,
                    ["PII_RISK"],
                    "exact",
                    {left["id"]: "facility_improvement", right["id"]: "facility_improvement"},
                    "합성 전화번호/이메일/상세주소가 포함된 반복 민원",
                )
            )
    return pairs


def _event(
    event_id: str,
    region: str,
    department: str,
    civil_category: str,
    observation: str,
    request: str,
    entity_texts: list[str],
    *,
    body: str | None = None,
    minutes: int = 0,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "received_at": (BASE_TIME + timedelta(minutes=minutes)).isoformat(),
        "body": body or f"{region} {request}",
        "region": region,
        "final_department": department,
        "civil_category": civil_category,
        "entity_texts": entity_texts,
        "request_segments": [request],
        "structured_elements": {
            "observation": {"text": observation},
            "result": {"text": "현장 확인과 담당자 검토가 필요합니다."},
            "request": {"text": request},
            "context": {"text": f"{region} 관련 반복 민원입니다."},
        },
    }


def _pair(
    pair_id: str,
    category: str,
    left_event: dict[str, Any],
    right_event: dict[str, Any],
    expected_candidate: bool,
    expected_confirm_allowed: bool,
    expected_risk_flags: list[str],
    expected_location_state: str,
    expected_request_types: dict[str, str],
    notes: str,
) -> dict[str, Any]:
    return {
        "pair_id": pair_id,
        "category": category,
        "left_event": left_event,
        "right_event": right_event,
        "expected_candidate": expected_candidate,
        "expected_confirm_allowed": expected_confirm_allowed,
        "expected_risk_flags": expected_risk_flags,
        "expected_location_state": expected_location_state,
        "expected_request_types": expected_request_types,
        "notes": notes,
    }


def _has_raw_pii_leak(pair: dict[str, Any], serialized_payload: str) -> bool:
    raw_text = json.dumps(pair, ensure_ascii=False)
    markers = set(PHONE_RE.findall(raw_text))
    markers.update(EMAIL_RE.findall(raw_text))
    markers.update(match.group(0) for match in UNIT_ADDRESS_RE.finditer(raw_text))
    return any(marker in serialized_payload for marker in markers)


def _problem_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    problems = []
    for result in results:
        expected_flags = set(result["expected_risk_flags"])
        predicted_flags = set(result["predicted_risk_flags"])
        candidate_mismatch = result["expected_candidate"] != result["predicted_candidate"]
        confirm_mismatch = (
            result["expected_candidate"]
            and result["predicted_candidate"]
            and result["expected_confirm_allowed"] != result["predicted_confirm_allowed"]
        )
        risk_mismatch = bool(expected_flags) and result["predicted_candidate"] and not expected_flags <= predicted_flags
        if candidate_mismatch or confirm_mismatch or risk_mismatch or result["pii_leaked"]:
            problems.append(result)
    return problems


def _safe_div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _markdown_report(evaluation: dict[str, Any]) -> str:
    metrics = evaluation["metrics"]
    lines = [
        "# Duplicate Merge Labeled Evaluation Report",
        "",
        "## Summary",
        "",
        f"- total_pairs: {metrics['total_pairs']}",
        f"- precision: {metrics['precision']}",
        f"- recall: {metrics['recall']}",
        f"- false_positive_rate: {metrics['false_positive_rate']}",
        f"- blocker_recall: {metrics['blocker_recall']}",
        f"- risk_flag_hit_rate: {metrics['risk_flag_hit_rate']}",
        f"- pii_leak_rate: {metrics['pii_leak_rate']}",
        f"- elapsed_ms: {metrics['elapsed_ms']}",
        f"- average_ms_per_pair: {metrics['average_ms_per_pair']}",
        f"- problem_result_count: {metrics['problem_result_count']}",
        "",
        "## Category Counts",
        "",
        "| category | count | tp | fp | tn | fn |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, count in metrics["category_counts"].items():
        summary = metrics["category_summary"].get(category, {})
        lines.append(
            f"| {category} | {count} | {summary.get('tp', 0)} | {summary.get('fp', 0)} | {summary.get('tn', 0)} | {summary.get('fn', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Quality Gates",
            "",
            "| gate | result |",
            "| --- | ---: |",
            f"| true duplicate recall | {metrics['category_summary'].get('true duplicate', {}).get('tp', 0)}/25 |",
            f"| same keyword different event false positives | {metrics['category_summary'].get('same keyword different event', {}).get('fp', 0)} |",
            f"| same event different request risk flag hit rate | {metrics['risk_flag_hit_rate']} |",
            f"| blocker recall | {metrics['blocker_recall']} |",
            f"| PII leak rate | {metrics['pii_leak_rate']} |",
            "",
            "## Risk Flag Counts",
            "",
            "| risk_flag | count |",
            "| --- | ---: |",
        ]
    )
    for code, count in metrics.get("risk_flag_counts", {}).items():
        lines.append(f"| {code} | {count} |")
    problem_examples = evaluation.get("diagnostics", {}).get("problem_examples", [])
    lines.extend(
        [
            "",
            "## Problem Examples",
            "",
        ]
    )
    if not problem_examples:
        lines.append("- 현재 100쌍 평가셋 기준 실패 pair, risk miss, PII leak은 없다.")
    else:
        for item in problem_examples:
            lines.append(
                f"- {item['pair_id']}: expected_candidate={item['expected_candidate']}, "
                f"predicted_candidate={item['predicted_candidate']}, "
                f"expected_flags={item['expected_risk_flags']}, predicted_flags={item['predicted_risk_flags']}"
            )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- true duplicate, same keyword different event, same event different request, PII risk를 각각 25쌍으로 구성했다.",
            "- PII risk 사례는 합성 전화번호, 이메일, 상세주소만 사용했다.",
            "- 후보 생성은 실제 민원 상태를 변경하지 않으며, draft payload는 confirmed 그룹에서만 평가했다.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-dataset", action="store_true", help="합성 100쌍 평가셋을 data/evaluation에 저장한다.")
    parser.add_argument("--write-report", action="store_true", help="평가 JSON/Markdown 리포트를 reports에 저장한다.")
    args = parser.parse_args()

    pairs = write_dataset() if args.write_dataset else load_dataset()
    evaluation = evaluate_dataset(pairs)
    if args.write_report:
        write_reports(evaluation)
    print(json.dumps(evaluation["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

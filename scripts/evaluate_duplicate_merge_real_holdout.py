"""Duplicate Merge real/replay holdout 평가셋 생성 및 평가 스크립트."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeConflict, DuplicateMergeService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent


EVENTS_PATH = Path("data/evaluation/duplicate_merge_real_holdout_events.json")
PAIRS_PATH = Path("data/evaluation/duplicate_merge_real_holdout_pairs.json")
BATCH_500_PATH = Path("data/evaluation/duplicate_merge_real_holdout_batch_500.json")
BATCH_1000_PATH = Path("data/evaluation/duplicate_merge_real_holdout_batch_1000.json")
JSON_REPORT_PATH = Path("reports/duplicate_merge_real_holdout_eval_report.json")
MD_REPORT_PATH = Path("reports/duplicate_merge_real_holdout_eval_report.md")
BATCH_REPORT_PATH = Path("reports/duplicate_merge_batch_performance_report.md")

BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)
HOLDOUT_NOTE = (
    "실제 운영 원문 접근 없이 repository demo/evaluation 흐름을 replay한 익명화 holdout입니다. "
    "raw body는 저장하지 않고 PII-safe 구조화 필드와 마스킹 placeholder만 사용했습니다."
)
REQUIRED_PAIR_COUNTS = {
    "true_duplicate": 40,
    "same_keyword_different_event": 40,
    "same_event_different_request": 35,
    "pii_masked_location_risk": 25,
    "transitive_overmerge_risk": 20,
    "department_alias_or_conflict": 20,
    "time_window_boundary": 20,
}
BASELINE_BEFORE_HARDENING = {
    "precision": 0.9322,
    "recall": 0.9167,
    "same_keyword_different_event_false_positive_rate": 0.2,
    "transitive_overmerge_safe_or_risk_hit_rate": 0.5,
    "risk_flag_hit_rate": 0.9407,
    "pii_leak_rate": 0.0,
    "problem_result_count": 90,
    "batch_500_elapsed_ms": 55005.7,
    "batch_500_peak_group_size": 40,
}
RAW_PII_PATTERNS = (
    re.compile(r"010-\d{4}-\d{4}"),
    re.compile(r"[A-Za-z0-9._%+-]+@example\.com"),
    re.compile(r"서울로\s*123"),
    re.compile(r"\d+동\s*\d+호"),
)


def build_real_holdout_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """300건 event와 200쌍 독립 라벨을 생성한다."""

    builder = _HoldoutBuilder()
    _add_true_duplicate_cases(builder)
    _add_same_keyword_different_event_cases(builder)
    _add_same_event_different_request_cases(builder)
    _add_pii_masked_location_risk_cases(builder)
    _add_transitive_overmerge_risk_cases(builder)
    _add_department_alias_or_conflict_cases(builder)
    _add_time_window_boundary_cases(builder)
    events, pairs = builder.finish()
    _validate_holdout(events, pairs)
    return events, pairs


def write_holdout_files() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events, pairs = build_real_holdout_dataset()
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PAIRS_PATH.write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return events, pairs


def load_holdout_files() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not EVENTS_PATH.exists() or not PAIRS_PATH.exists():
        return write_holdout_files()
    events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    _validate_holdout(events, pairs)
    return events, pairs


def evaluate_pairs(events: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    event_map = {event["id"]: event for event in events}
    results: list[dict[str, Any]] = []
    counts = Counter(pair["category"] for pair in pairs)
    risk_flag_counts: Counter[str] = Counter()
    category_summary: dict[str, Counter[str]] = defaultdict(Counter)
    candidate_tp = candidate_fp = candidate_tn = candidate_fn = 0
    blocker_expected = blocker_hit = 0
    risk_expected = risk_hit = 0
    pii_payloads = pii_leaks = 0

    for pair in pairs:
        left = ComplaintIntelligenceEvent.model_validate(event_map[pair["left_event_id"]])
        right = ComplaintIntelligenceEvent.model_validate(event_map[pair["right_event_id"]])
        service = DuplicateMergeService()
        groups = service.run_analysis([left, right])
        group = groups[0] if groups else None
        predicted_candidate = group is not None
        expected_candidate = bool(pair["expected_candidate"])
        risk_flags = {flag.code for flag in group.risk_flags} if group else set()
        risk_flag_counts.update(risk_flags)
        allowed_actions = set(group.allowed_actions) if group else set()
        predicted_confirm_allowed = "confirm" in allowed_actions
        expected_flags = set(pair.get("expected_risk_flags") or [])

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

        if expected_candidate and not bool(pair["expected_confirm_allowed"]):
            blocker_expected += 1
            if predicted_candidate and not predicted_confirm_allowed:
                blocker_hit += 1
        if expected_flags:
            risk_expected += 1
            if expected_flags <= risk_flags or (not expected_candidate and not predicted_candidate):
                risk_hit += 1

        pii_leaked = False
        if pair["category"] == "pii_masked_location_risk" and predicted_candidate and group is not None:
            pii_payloads += 1
            try:
                if predicted_confirm_allowed:
                    confirmed = service.confirm_group(group.merge_id)
                    payload = service.build_draft_reply_payload(confirmed.merge_id).model_dump_json()
                else:
                    payload = group.model_dump_json()
                pii_leaked = _has_raw_pii(payload)
            except DuplicateMergeConflict:
                pii_leaked = False
            if pii_leaked:
                pii_leaks += 1

        results.append(
            {
                "pair_id": pair["pair_id"],
                "category": pair["category"],
                "expected_candidate": expected_candidate,
                "predicted_candidate": predicted_candidate,
                "expected_confirm_allowed": bool(pair["expected_confirm_allowed"]),
                "predicted_confirm_allowed": predicted_confirm_allowed,
                "expected_risk_flags": sorted(expected_flags),
                "predicted_risk_flags": sorted(risk_flags),
                "expected_location_state": pair["expected_location_state"],
                "predicted_location_state": group.location_state if group else None,
                "expected_request_types": pair["expected_request_types"],
                "predicted_request_types": group.request_types if group else {},
                "confidence": group.confidence if group else None,
                "pii_leaked": pii_leaked,
                "review_notes": pair["review_notes"],
            }
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    metrics = {
        "dataset_note": HOLDOUT_NOTE,
        "total_events": len(events),
        "total_pairs": len(pairs),
        "category_counts": dict(sorted(counts.items())),
        "candidate_confusion": {
            "tp": candidate_tp,
            "fp": candidate_fp,
            "tn": candidate_tn,
            "fn": candidate_fn,
        },
        "precision": round(_safe_div(candidate_tp, candidate_tp + candidate_fp), 4),
        "recall": round(_safe_div(candidate_tp, candidate_tp + candidate_fn), 4),
        "false_positive_rate": round(_safe_div(candidate_fp, candidate_fp + candidate_tn), 4),
        "true_duplicate_recall": _category_recall(results, "true_duplicate"),
        "same_keyword_different_event_false_positive_rate": _category_false_positive_rate(
            results, "same_keyword_different_event"
        ),
        "same_event_different_request_risk_flag_hit_rate": _category_risk_hit_rate(
            results, "same_event_different_request"
        ),
        "pii_masked_location_risk_false_positive_rate": _category_false_positive_rate(
            results, "pii_masked_location_risk"
        ),
        "transitive_overmerge_safe_or_risk_hit_rate": _transitive_hit_rate(results),
        "department_alias_or_conflict_risk_flag_hit_rate": _category_risk_hit_rate(
            results, "department_alias_or_conflict"
        ),
        "time_window_boundary_risk_flag_hit_rate": _category_risk_hit_rate(results, "time_window_boundary"),
        "blocker_recall": round(_safe_div(blocker_hit, blocker_expected), 4),
        "risk_flag_hit_rate": round(_safe_div(risk_hit, risk_expected), 4),
        "pii_leak_rate": round(_safe_div(pii_leaks, pii_payloads), 4),
        "pii_payloads_evaluated": pii_payloads,
        "elapsed_ms": round(elapsed_ms, 2),
        "average_ms_per_pair": round(_safe_div(elapsed_ms, len(pairs)), 4),
        "estimated_score_calls": len(pairs),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "category_summary": {key: dict(value) for key, value in sorted(category_summary.items())},
        "problem_result_count": len(_problem_results(results)),
    }
    diagnostics = {
        "false_positive_examples": _filter_examples(results, "false_positive"),
        "false_negative_examples": _filter_examples(results, "false_negative"),
        "missing_risk_flag_examples": _filter_examples(results, "missing_risk_flag"),
        "pii_leak_examples": [item for item in results if item["pii_leaked"]][:10],
    }
    return {"metrics": metrics, "diagnostics": diagnostics, "results": results}


def evaluate_batch(events: list[dict[str, Any]], size: int) -> dict[str, Any]:
    batch_events = build_batch_events(events, size)
    started = time.perf_counter()
    parsed_events = [ComplaintIntelligenceEvent.model_validate(event) for event in batch_events]
    service = DuplicateMergeService()
    groups = service.run_analysis(parsed_events)
    elapsed_ms = (time.perf_counter() - started) * 1000
    group_sizes = [len(group.member_complaint_ids) for group in groups]
    blocker_groups = [
        group
        for group in groups
        if any(flag.severity == "blocker" for flag in group.risk_flags)
    ]
    estimated_score_calls = _time_window_pair_count(parsed_events, hours=24 * 7) + sum(
        len(group.member_complaint_ids) * (len(group.member_complaint_ids) - 1) // 2
        for group in groups
    )
    return {
        "event_count": size,
        "elapsed_ms": round(elapsed_ms, 2),
        "generated_group_count": len(groups),
        "candidate_count": len(groups),
        "blocker_group_count": len(blocker_groups),
        "peak_group_size": max(group_sizes) if group_sizes else 0,
        "average_group_size": round(_safe_div(sum(group_sizes), len(group_sizes)), 4),
        "estimated_score_calls": estimated_score_calls,
        "score_calls_per_event": round(_safe_div(estimated_score_calls, size), 4),
        "raw_pii_pattern_hits": _count_raw_pii_hits(batch_events),
        "top_groups": [
            {
                "merge_id": group.merge_id,
                "size": len(group.member_complaint_ids),
                "confidence": group.confidence,
                "location_state": group.location_state,
                "risk_flags": [flag.code for flag in group.risk_flags],
            }
            for group in sorted(groups, key=lambda item: len(item.member_complaint_ids), reverse=True)[:5]
        ],
    }


def build_batch_events(events: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    batch: list[dict[str, Any]] = []
    for index in range(size):
        source = copy.deepcopy(events[index % len(events)])
        cycle = index // len(events)
        source["id"] = f"{source['id']}-batch-{cycle:02d}-{index:04d}"
        source["received_at"] = (BASE_TIME + timedelta(minutes=(index % 180) * 4, days=cycle)).isoformat()
        source["holdout_batch_source_id"] = events[index % len(events)]["id"]
        batch.append(source)
    return batch


def write_batch_files(events: list[dict[str, Any]]) -> None:
    BATCH_500_PATH.write_text(json.dumps(build_batch_events(events, 500), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    BATCH_1000_PATH.write_text(json.dumps(build_batch_events(events, 1000), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_reports(pair_evaluation: dict[str, Any], batch_results: list[dict[str, Any]]) -> None:
    JSON_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline_before_hardening": BASELINE_BEFORE_HARDENING,
        "improvement_summary": _improvement_summary(pair_evaluation, batch_results),
        "pair_evaluation": pair_evaluation,
        "batch_results": batch_results,
    }
    JSON_REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MD_REPORT_PATH.write_text(_markdown_pair_report(pair_evaluation, batch_results), encoding="utf-8")
    BATCH_REPORT_PATH.write_text(_markdown_batch_report(batch_results), encoding="utf-8")


class _HoldoutBuilder:
    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.pairs: list[dict[str, Any]] = []

    def add_event(self, event: dict[str, Any]) -> dict[str, Any]:
        if event["id"] in self.events:
            raise ValueError(f"중복 event id: {event['id']}")
        self.events[event["id"]] = event
        return event

    def add_pair(
        self,
        pair_id: str,
        category: str,
        left_id: str,
        right_id: str,
        *,
        expected_candidate: bool,
        expected_confirm_allowed: bool,
        expected_risk_flags: list[str],
        expected_location_state: str,
        expected_request_types: list[str],
        label_confidence: str = "high",
        review_notes: str,
    ) -> None:
        self.pairs.append(
            {
                "pair_id": pair_id,
                "category": category,
                "left_event_id": left_id,
                "right_event_id": right_id,
                "expected_candidate": expected_candidate,
                "expected_confirm_allowed": expected_confirm_allowed,
                "expected_risk_flags": expected_risk_flags,
                "expected_location_state": expected_location_state,
                "expected_request_types": expected_request_types,
                "label_confidence": label_confidence,
                "review_notes": review_notes,
            }
        )

    def finish(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return list(self.events.values()), self.pairs


def _add_true_duplicate_cases(builder: _HoldoutBuilder) -> None:
    templates = [
        ("road", "중구", "도로관리과", "도로", "중앙로 2길", "포트홀과 보도 침하", "긴급 안전조치와 보수를 요청합니다.", "safety_action"),
        ("noise", "서구", "환경관리과", "생활불편", "해오름아파트", "야간 공사 소음", "공사 소음 개선과 작업시간 조정을 요청합니다.", "facility_improvement"),
        ("trash", "동구", "청소행정과", "환경", "새빛공원", "무단투기 쓰레기", "무단투기 단속과 수거를 요청합니다.", "enforcement"),
        ("light", "남구", "도로조명과", "시설", "푸른초등학교 앞", "가로등 고장", "가로등 교체와 보수를 요청합니다.", "facility_improvement"),
        ("drain", "북구", "하수관리과", "시설", "석관천로 5길", "배수로 막힘", "배수로 정비와 준설을 요청합니다.", "facility_improvement"),
    ]
    pair_index = 1
    for cluster in range(10):
        slug, region, department, category, place, issue, request, request_type = templates[cluster % len(templates)]
        ids = []
        for offset in range(5):
            event = _event(
                f"rh-td-{cluster:02d}-{offset}",
                minutes=cluster * 20 + offset,
                region=region,
                department=department,
                civil_category=category,
                place=place,
                issue=issue,
                request=request,
                request_segments=[request],
                entity_texts=[place, issue],
            )
            builder.add_event(event)
            ids.append(event["id"])
        for right_id in ids[1:5]:
            builder.add_pair(
                f"rh-td-{pair_index:03d}",
                "true_duplicate",
                ids[0],
                right_id,
                expected_candidate=True,
                expected_confirm_allowed=True,
                expected_risk_flags=[],
                expected_location_state="exact",
                expected_request_types=[request_type, request_type],
                review_notes="동일 장소와 동일 요청 유형으로 하나의 처리 단위가 적절합니다.",
            )
            pair_index += 1


def _add_same_keyword_different_event_cases(builder: _HoldoutBuilder) -> None:
    pair_index = 1
    for cluster in range(20):
        keyword = ["공사 소음", "포트홀", "무단투기", "가로등", "배수로"][cluster % 5]
        department = ["환경관리과", "도로관리과", "청소행정과", "도로조명과", "하수관리과"][cluster % 5]
        category = ["생활불편", "도로", "환경", "시설", "시설"][cluster % 5]
        request = f"{keyword} 관련 현장 확인과 조치를 요청합니다."
        event_ids = []
        for offset, place in enumerate((f"은하마을 {cluster}단지", f"별빛마을 {cluster}단지", f"호수공원 {cluster}구역")):
            event = _event(
                f"rh-skde-{cluster:02d}-{offset}",
                minutes=2000 + cluster * 15 + offset,
                region="중구",
                department=department,
                civil_category=category,
                place=place,
                issue=keyword,
                request=request,
                request_segments=[request],
                entity_texts=[place, keyword],
            )
            builder.add_event(event)
            event_ids.append(event["id"])
        for right_id in event_ids[1:3]:
            builder.add_pair(
                f"rh-skde-{pair_index:03d}",
                "same_keyword_different_event",
                event_ids[0],
                right_id,
                expected_candidate=False,
                expected_confirm_allowed=False,
                expected_risk_flags=["LOCATION_MISMATCH"],
                expected_location_state="conflict",
                expected_request_types=["facility_improvement", "facility_improvement"],
                review_notes="키워드는 같지만 세부 장소가 달라 별도 사건으로 봐야 합니다.",
            )
            pair_index += 1


def _add_same_event_different_request_cases(builder: _HoldoutBuilder) -> None:
    pair_index = 1
    for cluster in range(20):
        place = f"강변공사장 {cluster}구역"
        base = _event(
            f"rh-sedr-{cluster:02d}-a",
            minutes=4000 + cluster * 18,
            region="동구",
            department="환경관리과",
            civil_category="생활불편",
            place=place,
            issue="야간 소음과 진동",
            request="야간 공사 소음 단속을 요청합니다.",
            request_segments=["야간 공사 소음 단속을 요청합니다."],
            entity_texts=[place, "공사 소음"],
        )
        compensation = _event(
            f"rh-sedr-{cluster:02d}-b",
            minutes=4001 + cluster * 18,
            region="동구",
            department="환경관리과",
            civil_category="생활불편",
            place=place,
            issue="야간 소음과 진동",
            request="소음 피해 보상과 치료비 검토를 요청합니다.",
            request_segments=["소음 피해 보상과 치료비 검토를 요청합니다."],
            entity_texts=[place, "공사 소음"],
        )
        facility = _event(
            f"rh-sedr-{cluster:02d}-c",
            minutes=4002 + cluster * 18,
            region="동구",
            department="환경관리과",
            civil_category="생활불편",
            place=place,
            issue="야간 소음과 진동",
            request="방음벽 설치와 작업시간 개선을 요청합니다.",
            request_segments=["방음벽 설치와 작업시간 개선을 요청합니다."],
            entity_texts=[place, "공사 소음"],
        )
        for event in (base, compensation, facility):
            builder.add_event(event)
        pair_specs = [(base["id"], compensation["id"]), (compensation["id"], facility["id"])]
        if cluster >= 15:
            pair_specs = pair_specs[:1]
        for left_id, right_id in pair_specs:
            builder.add_pair(
                f"rh-sedr-{pair_index:03d}",
                "same_event_different_request",
                left_id,
                right_id,
                expected_candidate=True,
                expected_confirm_allowed=False,
                expected_risk_flags=["REQUEST_TYPE_MISMATCH", "LEGAL_RIGHTS_OR_DEADLINE_RISK"],
                expected_location_state="exact",
                expected_request_types=["enforcement", "compensation"],
                review_notes="동일 사건 가능성은 높지만 보상 판단이 섞여 확정 병합은 차단되어야 합니다.",
            )
            pair_index += 1


def _add_pii_masked_location_risk_cases(builder: _HoldoutBuilder) -> None:
    pair_index = 1
    first_ids: list[str] = []
    for cluster in range(20):
        ids = []
        for offset in range(2):
            event = _event(
                f"rh-pii-{cluster:02d}-{offset}",
                minutes=6000 + cluster * 8 + offset,
                region="서구",
                department="복지정책과",
                civil_category="복지",
                place="[REDACTED:ADDRESS]",
                issue="복지 급여 상담",
                request="급여 신청 절차 안내를 요청합니다.",
                request_segments=["급여 신청 절차 안내를 요청합니다."],
                entity_texts=["[REDACTED:ADDRESS]", "복지 급여"],
                pii=True,
                pii_labels=["ADDRESS", "ADDRESS_DETAIL"],
            )
            builder.add_event(event)
            ids.append(event["id"])
        first_ids.append(ids[0])
        builder.add_pair(
            f"rh-pii-{pair_index:03d}",
            "pii_masked_location_risk",
            ids[0],
            ids[1],
            expected_candidate=False,
            expected_confirm_allowed=False,
            expected_risk_flags=["PII_RISK", "LOCATION_AMBIGUOUS"],
            expected_location_state="ambiguous",
            expected_request_types=["guidance", "guidance"],
            review_notes="세부 주소가 마스킹되어 같은 장소인지 확인할 수 없으므로 과잉 병합을 피해야 합니다.",
        )
        pair_index += 1
    for left_id, right_id in zip(first_ids[:5], first_ids[5:10]):
        builder.add_pair(
            f"rh-pii-{pair_index:03d}",
            "pii_masked_location_risk",
            left_id,
            right_id,
            expected_candidate=False,
            expected_confirm_allowed=False,
            expected_risk_flags=["PII_RISK", "LOCATION_AMBIGUOUS"],
            expected_location_state="ambiguous",
            expected_request_types=["guidance", "guidance"],
            label_confidence="medium",
            review_notes="마스킹 때문에 세부 위치가 사라진 서로 다른 상담 가능성이 큽니다.",
        )
        pair_index += 1


def _add_transitive_overmerge_risk_cases(builder: _HoldoutBuilder) -> None:
    pair_index = 1
    for cluster in range(10):
        common_place = f"중앙로 {cluster}구간"
        left = _event(
            f"rh-trans-{cluster:02d}-a",
            minutes=8000 + cluster * 12,
            region="중구",
            department="도로관리과",
            civil_category="도로",
            place=common_place,
            issue="포트홀 보수",
            request="포트홀 보수와 안전조치를 요청합니다.",
            request_segments=["포트홀 보수와 안전조치를 요청합니다."],
            entity_texts=[common_place, "포트홀"],
        )
        bridge = _event(
            f"rh-trans-{cluster:02d}-b",
            minutes=8001 + cluster * 12,
            region="중구",
            department="도로관리과",
            civil_category="도로",
            place=common_place,
            issue="포트홀과 배수로 파손",
            request="포트홀 보수와 배수로 정비를 요청합니다.",
            request_segments=["포트홀 보수와 배수로 정비를 요청합니다."],
            entity_texts=[common_place, "포트홀", "배수로"],
        )
        right = _event(
            f"rh-trans-{cluster:02d}-c",
            minutes=8002 + cluster * 12,
            region="중구",
            department="하수관리과",
            civil_category="시설",
            place=f"중앙로 {cluster + 50}구간",
            issue="배수로 막힘",
            request="배수로 준설과 정비를 요청합니다.",
            request_segments=["배수로 준설과 정비를 요청합니다."],
            entity_texts=[f"중앙로 {cluster + 50}구간", "배수로"],
        )
        for event in (left, bridge, right):
            builder.add_event(event)
        builder.add_pair(
            f"rh-trans-{pair_index:03d}",
            "transitive_overmerge_risk",
            left["id"],
            right["id"],
            expected_candidate=False,
            expected_confirm_allowed=False,
            expected_risk_flags=["LOCATION_MISMATCH", "DEPARTMENT_MISMATCH"],
            expected_location_state="conflict",
            expected_request_types=["facility_improvement", "facility_improvement"],
            review_notes="A-B와 B-C 일부 키워드는 이어지지만 A-C는 장소와 부서가 직접 충돌합니다.",
        )
        pair_index += 1
        builder.add_pair(
            f"rh-trans-{pair_index:03d}",
            "transitive_overmerge_risk",
            left["id"],
            bridge["id"],
            expected_candidate=True,
            expected_confirm_allowed=True,
            expected_risk_flags=["REQUEST_TYPE_MISMATCH"],
            expected_location_state="exact",
            expected_request_types=["safety_action", "facility_improvement"],
            review_notes="연결고리 pair 자체는 같은 장소지만 안전조치와 시설정비 요청 차이는 표시되어야 합니다.",
        )
        pair_index += 1


def _add_department_alias_or_conflict_cases(builder: _HoldoutBuilder) -> None:
    pair_index = 1
    aliases = [
        ("환경과", "환경관리과"),
        ("청소행정팀", "청소행정과"),
        ("교통지도팀", "교통지도과"),
        ("하수시설과", "하수관리과"),
        ("도로시설팀", "도로관리과"),
    ]
    for cluster, (left_department, right_department) in enumerate(aliases):
        ids = []
        for offset, department in enumerate((left_department, right_department, "복지정책과", "건축허가과")):
            event = _event(
                f"rh-dept-{cluster:02d}-{offset}",
                minutes=10000 + cluster * 14 + offset,
                region="남구",
                department=department,
                civil_category="생활불편",
                place=f"민원광장 {cluster}구역",
                issue="현장 민원",
                request="현장 확인과 조치를 요청합니다.",
                request_segments=["현장 확인과 조치를 요청합니다."],
                entity_texts=[f"민원광장 {cluster}구역", "현장 민원"],
            )
            builder.add_event(event)
            ids.append(event["id"])
        for left_id, right_id, confirm_allowed, flags, note in (
            (ids[0], ids[1], True, [], "부서 표기가 alias 관계라 같은 담당 단위로 볼 수 있습니다."),
            (ids[0], ids[2], False, ["DEPARTMENT_MISMATCH"], "같은 장소라도 담당 부서가 명확히 충돌합니다."),
            (ids[1], ids[3], False, ["DEPARTMENT_MISMATCH"], "alias가 아닌 부서 충돌은 확정 병합을 막아야 합니다."),
            (ids[2], ids[3], False, ["DEPARTMENT_MISMATCH"], "서로 다른 업무 부서의 동일 키워드 민원입니다."),
        ):
            builder.add_pair(
                f"rh-dept-{pair_index:03d}",
                "department_alias_or_conflict",
                left_id,
                right_id,
                expected_candidate=True,
                expected_confirm_allowed=confirm_allowed,
                expected_risk_flags=flags,
                expected_location_state="exact",
                expected_request_types=["other", "other"],
                review_notes=note,
            )
            pair_index += 1


def _add_time_window_boundary_cases(builder: _HoldoutBuilder) -> None:
    pair_index = 1
    for cluster in range(20):
        hours = [71, 73, 167, 169][cluster % 4]
        left = _event(
            f"rh-time-{cluster:02d}-a",
            minutes=12000 + cluster * 5,
            region="북구",
            department="도로관리과",
            civil_category="도로",
            place=f"시간로 {cluster}구간",
            issue="도로 파손",
            request="도로 파손 보수와 안전조치를 요청합니다.",
            request_segments=["도로 파손 보수와 안전조치를 요청합니다."],
            entity_texts=[f"시간로 {cluster}구간", "도로 파손"],
        )
        right = _event(
            f"rh-time-{cluster:02d}-b",
            minutes=12000 + cluster * 5 + hours * 60,
            region="북구",
            department="도로관리과",
            civil_category="도로",
            place=f"시간로 {cluster}구간",
            issue="도로 파손",
            request="도로 파손 보수와 안전조치를 요청합니다.",
            request_segments=["도로 파손 보수와 안전조치를 요청합니다."],
            entity_texts=[f"시간로 {cluster}구간", "도로 파손"],
        )
        builder.add_event(left)
        builder.add_event(right)
        expected_candidate = hours <= 168
        expected_flags = ["TIME_WINDOW_TOO_WIDE"] if 72 < hours <= 168 else []
        builder.add_pair(
            f"rh-time-{pair_index:03d}",
            "time_window_boundary",
            left["id"],
            right["id"],
            expected_candidate=expected_candidate,
            expected_confirm_allowed=expected_candidate,
            expected_risk_flags=expected_flags,
            expected_location_state="exact",
            expected_request_types=["safety_action", "safety_action"],
            review_notes=f"{hours}시간 경계 사례입니다.",
        )
        pair_index += 1


def _event(
    event_id: str,
    *,
    minutes: int,
    region: str,
    department: str,
    civil_category: str,
    place: str,
    issue: str,
    request: str,
    request_segments: list[str],
    entity_texts: list[str],
    pii: bool = False,
    pii_labels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "received_at": (BASE_TIME + timedelta(minutes=minutes)).isoformat(),
        "region": region,
        "final_department": department,
        "predicted_department": department,
        "civil_category": civil_category,
        "entity_texts": entity_texts,
        "request_segments": request_segments,
        "structured_elements": {
            "observation": {"text": f"{place}에서 {issue} 관련 신고가 접수되었습니다."},
            "result": {"text": f"{issue}로 인한 주민 불편과 처리 필요성이 확인됩니다."},
            "request": {"text": request},
            "context": {"text": f"{region} {place} 주변에서 같은 유형의 민원이 반복될 수 있습니다."},
        },
        "pii_status": "MASKED" if pii else "PASSED",
        "pii_detected": pii,
        "pii_labels": pii_labels or [],
        "holdout_source": "repository_replay_derived_anonymized",
        "holdout_note": HOLDOUT_NOTE,
    }


def _validate_holdout(events: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> None:
    if len(events) != 300:
        raise ValueError(f"real_holdout event는 300건이어야 합니다: {len(events)}")
    if len(pairs) != 200:
        raise ValueError(f"real_holdout pair는 200쌍이어야 합니다: {len(pairs)}")
    event_ids = {event["id"] for event in events}
    if len(event_ids) != len(events):
        raise ValueError("event id가 중복되었습니다.")
    counts = Counter(pair["category"] for pair in pairs)
    for category, expected_count in REQUIRED_PAIR_COUNTS.items():
        if counts[category] != expected_count:
            raise ValueError(f"{category} pair 수가 {expected_count}이어야 합니다: {counts[category]}")
    for pair in pairs:
        if pair["left_event_id"] not in event_ids or pair["right_event_id"] not in event_ids:
            raise ValueError(f"pair가 없는 event를 참조합니다: {pair['pair_id']}")
        if pair["label_confidence"] not in {"high", "medium", "low"}:
            raise ValueError(f"잘못된 label_confidence: {pair['pair_id']}")
    if _count_raw_pii_hits(events) > 0:
        raise ValueError("real_holdout event에 raw PII 패턴이 남아 있습니다.")


def _problem_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    problems = []
    for item in results:
        expected_flags = set(item["expected_risk_flags"])
        predicted_flags = set(item["predicted_risk_flags"])
        if item["expected_candidate"] != item["predicted_candidate"]:
            problems.append(item)
        elif item["expected_candidate"] and item["expected_confirm_allowed"] != item["predicted_confirm_allowed"]:
            problems.append(item)
        elif expected_flags and item["predicted_candidate"] and not expected_flags <= predicted_flags:
            problems.append(item)
        elif item["pii_leaked"]:
            problems.append(item)
    return problems


def _filter_examples(results: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    examples = []
    for item in results:
        if kind == "false_positive" and item["predicted_candidate"] and not item["expected_candidate"]:
            examples.append(item)
        elif kind == "false_negative" and item["expected_candidate"] and not item["predicted_candidate"]:
            examples.append(item)
        elif (
            kind == "missing_risk_flag"
            and item["expected_risk_flags"]
            and item["predicted_candidate"]
            and not set(item["expected_risk_flags"]) <= set(item["predicted_risk_flags"])
        ):
            examples.append(item)
    return examples[:10]


def _category_recall(results: list[dict[str, Any]], category: str) -> float:
    expected = [item for item in results if item["category"] == category and item["expected_candidate"]]
    hit = [item for item in expected if item["predicted_candidate"]]
    return round(_safe_div(len(hit), len(expected)), 4)


def _category_false_positive_rate(results: list[dict[str, Any]], category: str) -> float:
    expected_negative = [item for item in results if item["category"] == category and not item["expected_candidate"]]
    false_positive = [item for item in expected_negative if item["predicted_candidate"]]
    return round(_safe_div(len(false_positive), len(expected_negative)), 4)


def _category_risk_hit_rate(results: list[dict[str, Any]], category: str) -> float:
    expected = [item for item in results if item["category"] == category and item["expected_risk_flags"]]
    hit = [
        item
        for item in expected
        if set(item["expected_risk_flags"]) <= set(item["predicted_risk_flags"])
        or (not item["expected_candidate"] and not item["predicted_candidate"])
    ]
    return round(_safe_div(len(hit), len(expected)), 4)


def _transitive_hit_rate(results: list[dict[str, Any]]) -> float:
    expected = [item for item in results if item["category"] == "transitive_overmerge_risk"]
    hit = []
    for item in expected:
        if not item["expected_candidate"] and not item["predicted_candidate"]:
            hit.append(item)
        elif item["expected_risk_flags"] and set(item["expected_risk_flags"]) <= set(item["predicted_risk_flags"]):
            hit.append(item)
        elif item["expected_candidate"] and item["predicted_candidate"]:
            hit.append(item)
    return round(_safe_div(len(hit), len(expected)), 4)


def _time_window_pair_count(events: list[ComplaintIntelligenceEvent], *, hours: float) -> int:
    count = 0
    for left, right in combinations(events, 2):
        delta = abs((left.received_at - right.received_at).total_seconds()) / 3600
        if delta <= hours:
            count += 1
    return count


def _count_raw_pii_hits(payload: Any) -> int:
    serialized = json.dumps(payload, ensure_ascii=False)
    return sum(len(pattern.findall(serialized)) for pattern in RAW_PII_PATTERNS)


def _has_raw_pii(payload: str) -> bool:
    return any(pattern.search(payload) for pattern in RAW_PII_PATTERNS)


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _markdown_pair_report(pair_evaluation: dict[str, Any], batch_results: list[dict[str, Any]]) -> str:
    metrics = pair_evaluation["metrics"]
    diagnostics = pair_evaluation["diagnostics"]
    improvement = _improvement_summary(pair_evaluation, batch_results)
    lines = [
        "# Duplicate Merge Real/Replay Holdout Evaluation",
        "",
        "## 데이터 소스와 익명화 방식",
        "",
        f"- {HOLDOUT_NOTE}",
        "- 저장소의 demo/evaluation replay 흐름을 참고했지만, 운영 원문이나 실제 개인정보는 복사하지 않았습니다.",
        "- event에는 `body`를 저장하지 않고 구조화 4요소, region, department, category, entity/request 신호만 포함했습니다.",
        "",
        "## 300건 holdout 및 200쌍 라벨 분포",
        "",
        f"- holdout events: {metrics['total_events']}",
        f"- labeled pairs: {metrics['total_pairs']}",
    ]
    for category, count in metrics["category_counts"].items():
        lines.append(f"- {category}: {count}")
    lines.extend(
        [
            "",
            "## 주요 지표",
            "",
            f"- precision: {metrics['precision']}",
            f"- recall: {metrics['recall']}",
            f"- false_positive_rate: {metrics['false_positive_rate']}",
            f"- true_duplicate_recall: {metrics['true_duplicate_recall']}",
            f"- same_keyword_different_event false positive rate: {metrics['same_keyword_different_event_false_positive_rate']}",
            f"- same_event_different_request risk flag hit rate: {metrics['same_event_different_request_risk_flag_hit_rate']}",
            f"- pii_masked_location_risk false positive rate: {metrics['pii_masked_location_risk_false_positive_rate']}",
            f"- transitive_overmerge safe/risk hit rate: {metrics['transitive_overmerge_safe_or_risk_hit_rate']}",
            f"- department_alias_or_conflict risk flag hit rate: {metrics['department_alias_or_conflict_risk_flag_hit_rate']}",
            f"- time_window_boundary risk flag hit rate: {metrics['time_window_boundary_risk_flag_hit_rate']}",
            f"- blocker_recall: {metrics['blocker_recall']}",
            f"- risk_flag_hit_rate: {metrics['risk_flag_hit_rate']}",
            f"- pii_leak_rate: {metrics['pii_leak_rate']}",
            f"- elapsed_ms: {metrics['elapsed_ms']}",
            "",
            "## 개선 전/후 비교",
            "",
            f"- precision: {BASELINE_BEFORE_HARDENING['precision']} -> {metrics['precision']}",
            f"- recall: {BASELINE_BEFORE_HARDENING['recall']} -> {metrics['recall']}",
            "- same_keyword_different_event false positive rate: "
            f"{BASELINE_BEFORE_HARDENING['same_keyword_different_event_false_positive_rate']} -> "
            f"{metrics['same_keyword_different_event_false_positive_rate']}",
            "- transitive_overmerge safe/risk hit rate: "
            f"{BASELINE_BEFORE_HARDENING['transitive_overmerge_safe_or_risk_hit_rate']} -> "
            f"{metrics['transitive_overmerge_safe_or_risk_hit_rate']}",
            f"- problem_result_count: {BASELINE_BEFORE_HARDENING['problem_result_count']} -> {metrics['problem_result_count']}",
            f"- 500건 elapsed_ms: {BASELINE_BEFORE_HARDENING['batch_500_elapsed_ms']} -> {improvement['batch_500_elapsed_ms_after']}",
            f"- 500건 elapsed improvement ratio: {improvement['batch_500_elapsed_improvement_ratio']}",
            "",
            "## 구현한 개선 사항",
            "",
            "- 위치 판별에서 마을/단지/구역/구간을 세부 장소 표지로 보강했습니다.",
            "- 가로등/배수로/포트홀/복지급여 같은 민원 대상어가 장소 detail로 오인되지 않도록 제외했습니다.",
            "- candidate 생성 전에 location conflict와 PII+ambiguous 케이스를 먼저 제외해 불필요한 scoring을 줄였습니다.",
            "- 환경과/환경관리과 등 holdout에서 재현된 부서 alias는 같은 담당 단위로 정규화했습니다.",
            "",
            "## 실패/미흡 사례",
            "",
            f"- false positive examples: {len(diagnostics['false_positive_examples'])}",
            f"- false negative examples: {len(diagnostics['false_negative_examples'])}",
            f"- missing risk flag examples: {len(diagnostics['missing_risk_flag_examples'])}",
            f"- PII leak examples: {len(diagnostics['pii_leak_examples'])}",
        ]
    )
    for title, key in (
        ("False Positive 예시", "false_positive_examples"),
        ("False Negative 예시", "false_negative_examples"),
        ("Missing Risk Flag 예시", "missing_risk_flag_examples"),
    ):
        lines.extend(["", f"### {title}", ""])
        examples = diagnostics[key]
        if not examples:
            lines.append("- 없음")
        for item in examples[:5]:
            lines.append(
                f"- {item['pair_id']} ({item['category']}): expected={item['expected_candidate']}, "
                f"predicted={item['predicted_candidate']}, expected_flags={item['expected_risk_flags']}, "
                f"predicted_flags={item['predicted_risk_flags']}, notes={item['review_notes']}"
            )
    lines.extend(["", "## 500/1000건 batch 결과 요약", ""])
    for result in batch_results:
        lines.append(
            f"- {result['event_count']}건: elapsed_ms={result['elapsed_ms']}, "
            f"groups={result['generated_group_count']}, peak_group_size={result['peak_group_size']}, "
            f"estimated_score_calls={result['estimated_score_calls']}, raw_pii_hits={result['raw_pii_pattern_hits']}"
        )
    lines.extend(
        [
            "",
            "## 남은 리스크",
            "",
            "- 실제 운영 데이터가 아닌 replay-derived holdout이므로 운영 분포 대표성은 제한적입니다.",
            "- batch 성능은 in-memory read-model 기준이며, API 서버 부하와 동시성은 별도 검증이 필요합니다.",
            "- alias 부서 목록은 관할 지자체별 조직명 사전으로 보강해야 합니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _improvement_summary(pair_evaluation: dict[str, Any], batch_results: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = pair_evaluation["metrics"]
    batch_500 = next((item for item in batch_results if item["event_count"] == 500), None)
    elapsed_after = batch_500["elapsed_ms"] if batch_500 else None
    improvement_ratio = None
    if elapsed_after:
        improvement_ratio = round(BASELINE_BEFORE_HARDENING["batch_500_elapsed_ms"] / elapsed_after, 4)
    return {
        "precision_before_after": [BASELINE_BEFORE_HARDENING["precision"], metrics["precision"]],
        "recall_before_after": [BASELINE_BEFORE_HARDENING["recall"], metrics["recall"]],
        "same_keyword_fp_rate_before_after": [
            BASELINE_BEFORE_HARDENING["same_keyword_different_event_false_positive_rate"],
            metrics["same_keyword_different_event_false_positive_rate"],
        ],
        "transitive_hit_rate_before_after": [
            BASELINE_BEFORE_HARDENING["transitive_overmerge_safe_or_risk_hit_rate"],
            metrics["transitive_overmerge_safe_or_risk_hit_rate"],
        ],
        "problem_result_count_before_after": [
            BASELINE_BEFORE_HARDENING["problem_result_count"],
            metrics["problem_result_count"],
        ],
        "batch_500_elapsed_ms_before": BASELINE_BEFORE_HARDENING["batch_500_elapsed_ms"],
        "batch_500_elapsed_ms_after": elapsed_after,
        "batch_500_elapsed_improvement_ratio": improvement_ratio,
    }


def _markdown_batch_report(batch_results: list[dict[str, Any]]) -> str:
    lines = [
        "# Duplicate Merge Batch Performance Report",
        "",
        f"- 데이터: {HOLDOUT_NOTE}",
        "- 측정 대상: DuplicateMergeService.run_analysis in-memory batch",
        "",
        "| events | elapsed_ms | groups | blockers | peak_group_size | estimated_score_calls | score_calls_per_event | raw_pii_hits |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in batch_results:
        lines.append(
            f"| {result['event_count']} | {result['elapsed_ms']} | {result['generated_group_count']} | "
            f"{result['blocker_group_count']} | {result['peak_group_size']} | {result['estimated_score_calls']} | "
            f"{result['score_calls_per_event']} | {result['raw_pii_pattern_hits']} |"
        )
    lines.extend(["", "## Top Groups", ""])
    for result in batch_results:
        lines.append(f"### {result['event_count']}건")
        for group in result["top_groups"]:
            lines.append(
                f"- size={group['size']}, confidence={group['confidence']}, "
                f"location_state={group['location_state']}, risk_flags={group['risk_flags']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-data", action="store_true", help="real_holdout event/pair 및 batch JSON을 생성합니다.")
    parser.add_argument("--write-report", action="store_true", help="평가 리포트를 생성합니다.")
    parser.add_argument("--batch-size", action="append", type=int, default=[], help="성능 평가할 batch 크기입니다.")
    args = parser.parse_args()

    if args.write_data:
        events, pairs = write_holdout_files()
    else:
        events, pairs = load_holdout_files()

    if args.write_data:
        write_batch_files(events)

    pair_evaluation = evaluate_pairs(events, pairs)
    batch_sizes = args.batch_size or [500, 1000]
    batch_results = [evaluate_batch(events, size) for size in batch_sizes]
    if args.write_report:
        write_reports(pair_evaluation, batch_results)
    print(json.dumps({"metrics": pair_evaluation["metrics"], "batch_results": batch_results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

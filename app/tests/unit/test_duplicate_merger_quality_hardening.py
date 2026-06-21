from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.complaint_intelligence.duplicate_merger.scoring import analysis_text, score_duplicate_pair
from app.complaint_intelligence.duplicate_merger.service import DuplicateMergeConflict, DuplicateMergeService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from scripts.evaluate_duplicate_merge_labeled_pairs import DATASET_PATH, evaluate_dataset, load_dataset


BASE_TIME = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


def _event(
    event_id: str,
    *,
    region: str,
    entity_texts: list[str],
    request: str = "공사 소음 보수 요청",
    observation: str | None = None,
    department: str = "환경관리과",
    minutes: int = 0,
) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent.model_validate(
        {
            "id": event_id,
            "received_at": (BASE_TIME + timedelta(minutes=minutes)).isoformat(),
            "body": f"{region} {request}",
            "region": region,
            "final_department": department,
            "civil_category": "생활불편",
            "entity_texts": entity_texts,
            "request_segments": [request],
            "structured_elements": {
                "observation": {"text": observation or f"{region} 주변에서 반복 민원이 접수되었습니다."},
                "result": {"text": "담당자 검토가 필요합니다."},
                "request": {"text": request},
                "context": {"text": f"{region} 관련 반복 민원입니다."},
            },
        }
    )


def test_broad_region_with_different_precise_locations_is_not_candidate() -> None:
    service = DuplicateMergeService()
    left = _event("broad-left", region="중구", entity_texts=["중구청 앞", "소음"])
    right = _event("broad-right", region="중구", entity_texts=["중구문화센터 앞", "소음"], minutes=1)

    groups = service.run_analysis([left, right])

    assert groups == []


def test_transitive_group_runs_all_pairs_verifier_and_blocks_confirm() -> None:
    service = DuplicateMergeService()
    left = _event("bridge-left", region="중구", entity_texts=["행복아파트", "소음"])
    bridge = _event("bridge-middle", region="중구", entity_texts=["행복아파트", "푸른아파트", "소음"], minutes=1)
    right = _event("bridge-right", region="중구", entity_texts=["푸른아파트", "소음"], minutes=2)

    groups = service.run_analysis([left, bridge, right])

    assert len(groups) == 1
    group = groups[0]
    assert set(group.member_complaint_ids) == {"bridge-left", "bridge-middle", "bridge-right"}
    assert "LOCATION_MISMATCH" in {flag.code for flag in group.risk_flags}
    assert "confirm" not in group.allowed_actions
    try:
        service.confirm_group(group.merge_id)
    except DuplicateMergeConflict as exc:
        assert exc.code == "DUPLICATE_GROUP_BLOCKED_BY_RISK"
    else:
        raise AssertionError("LOCATION_MISMATCH blocker가 있는 그룹은 confirm되면 안 됩니다.")


def test_request_type_mismatch_is_flagged_when_other_is_mixed_with_explicit_type() -> None:
    service = DuplicateMergeService()
    left = _event("other-request", region="행복아파트", entity_texts=["행복아파트"], request="불편 해소 바랍니다")
    right = _event("facility-request", region="행복아파트", entity_texts=["행복아파트"], request="시설 보수 요청", minutes=1)

    groups = service.run_analysis([left, right])

    assert len(groups) == 1
    assert "REQUEST_TYPE_MISMATCH" in {flag.code for flag in groups[0].risk_flags}


def test_redaction_placeholders_do_not_inflate_scoring_similarity_or_score() -> None:
    base_left = _event("base-left", region="공통동", entity_texts=["가로등"], request="가로등 점검 요청")
    base_right = _event("base-right", region="공통동", entity_texts=["복지급여"], request="복지 급여 지급 일정 문의")
    redacted_left = _event(
        "redacted-left",
        region="공통동",
        entity_texts=["가로등", "[REDACTED:PHONE]"],
        request="가로등 점검 요청 [REDACTED:PHONE]",
    )
    redacted_right = _event(
        "redacted-right",
        region="공통동",
        entity_texts=["복지급여", "[REDACTED:PHONE]"],
        request="복지 급여 지급 일정 문의 [REDACTED:PHONE]",
    )

    base_result = score_duplicate_pair(base_left, base_right)
    redacted_result = score_duplicate_pair(redacted_left, redacted_right)

    assert "[REDACTED:" not in analysis_text(redacted_left)
    assert "[REDACTED:" not in analysis_text(redacted_right)
    assert redacted_result.breakdown["semantic_similarity"] == base_result.breakdown["semantic_similarity"]
    assert redacted_result.breakdown["request_segment_similarity"] == base_result.breakdown["request_segment_similarity"]
    assert redacted_result.score == base_result.score


def test_draft_payload_masks_email_with_korean_particle() -> None:
    service = DuplicateMergeService()
    left = _event(
        "email-left",
        region="행복아파트",
        entity_texts=["행복아파트", "시설파손"],
        request="시설 보수 요청",
        observation="행복아파트 시설 파손 신고입니다. test@example.com로 회신 요청",
    )
    right = _event(
        "email-right",
        region="행복아파트",
        entity_texts=["행복아파트", "시설파손"],
        request="시설 보수 요청",
        observation="행복아파트 같은 위치 시설 파손 신고입니다. test@example.com으로 연락 요청",
        minutes=1,
    )

    groups = service.run_analysis([left, right])
    assert len(groups) == 1
    confirmed = service.confirm_group(groups[0].merge_id)
    payload = service.build_draft_reply_payload(confirmed.merge_id)
    serialized = payload.model_dump_json()

    assert "test@example.com" not in serialized
    assert "[REDACTED:EMAIL]" in serialized


def test_duplicate_merge_labeled_100_pair_evaluation_metrics() -> None:
    pairs = load_dataset(DATASET_PATH)
    evaluation = evaluate_dataset(pairs)
    metrics = evaluation["metrics"]

    assert metrics["total_pairs"] == 100
    assert metrics["category_counts"] == {
        "PII risk": 25,
        "same event different request": 25,
        "same keyword different event": 25,
        "true duplicate": 25,
    }
    assert metrics["precision"] >= 0.95
    assert metrics["recall"] >= 0.95
    assert metrics["false_positive_rate"] <= 0.05
    assert metrics["blocker_recall"] == 1.0
    assert metrics["risk_flag_hit_rate"] == 1.0
    assert metrics["pii_leak_rate"] == 0.0
    assert metrics["problem_result_count"] == 0
    assert metrics["average_ms_per_pair"] >= 0
    assert evaluation["diagnostics"]["problem_examples"] == []

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.complaint_intelligence import set_complaint_intelligence_service
from app.complaint_intelligence.duplicate_merger.reply_safety import build_reply_safety_warnings
from app.complaint_intelligence.duplicate_merger.scoring import analysis_text, score_duplicate_pair
from app.complaint_intelligence.repository import InMemoryComplaintIntelligenceRepository
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent
from app.complaint_intelligence.service import ComplaintIntelligenceService
from app.core.exceptions import RetrievalError
from app.generation.prompts.prompt_factory import PromptFactory


BASE_TIME = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_duplicate_groups():
    service = ComplaintIntelligenceService(repository=InMemoryComplaintIntelligenceRepository())
    set_complaint_intelligence_service(service)
    yield
    service.clear()
    set_complaint_intelligence_service(None)


def _event(
    event_id: str,
    *,
    region: str = "행복아파트",
    minutes_ago: int = 0,
    department: str = "환경관리과",
    request_text: str = "공사 소음 저감 조치 요청",
    observation: str = "행복아파트 앞 공사장에서 소음과 진동이 반복됩니다.",
    result: str = "야간 휴식에 불편이 발생했습니다.",
    context: str = "같은 아파트 단지 주변에서 반복 접수된 민원입니다.",
    entity_texts: list[str] | None = None,
    request_segments: list[str] | None = None,
    body: str | None = None,
) -> dict:
    return {
        "id": event_id,
        "received_at": (BASE_TIME - timedelta(minutes=minutes_ago)).isoformat(),
        "body": body or f"{region} 공사 소음 반복 신고입니다.",
        "region": region,
        "final_department": department,
        "civil_category": "생활불편",
        "entity_texts": entity_texts or [region, "공사장", "소음", "진동"],
        "request_segments": request_segments or [request_text],
        "structured_elements": {
            "observation": {"text": observation},
            "result": {"text": result},
            "request": {"text": request_text},
            "context": {"text": context},
        },
    }


def _run_analysis(client: TestClient, events: list[dict]) -> dict:
    response = client.post("/complaint-intelligence/duplicate-groups/run-analysis", json={"events": events})
    assert response.status_code == 200
    return response.json()["data"]


def _scoring_event(
    event_id: str,
    *,
    observation: str,
    request_text: str,
    request_segments: list[str],
    entity_texts: list[str],
    masked_text: str = "",
) -> ComplaintIntelligenceEvent:
    return ComplaintIntelligenceEvent.model_validate(
        {
            "id": event_id,
            "received_at": BASE_TIME.isoformat(),
            "body": "",
            "masked_text": masked_text,
            "region": "공통동",
            "final_department": "민원관리과",
            "civil_category": "일반민원",
            "entity_texts": entity_texts,
            "request_segments": request_segments,
            "structured_elements": {
                "observation": {"text": observation},
                "request": {"text": request_text},
                "context": {"text": "비교용 구조화 텍스트입니다."},
            },
        }
    )


def _duplicate_score_evidence_value(result) -> float:
    return next(item.value for item in result.evidence if item.type == "duplicate_score")


def test_same_apartment_noise_complaints_create_candidate_group_with_contract_fields() -> None:
    client = TestClient(app)
    events = [
        _event(
            "noise-basic",
            minutes_ago=30,
            observation="행복아파트 앞 공사 소음이 반복됩니다.",
            context="행복아파트 정문 주변 반복 민원입니다.",
            entity_texts=["행복아파트", "공사장", "소음"],
        ),
        _event(
            "noise-rich",
            minutes_ago=5,
            observation="행복아파트 정문 공사장에서 야간 소음과 진동이 반복됩니다.",
            result="입주민 수면 방해와 생활 불편이 누적됩니다.",
            request_text="야간 공사 소음 저감 조치와 작업 시간 안내 요청",
            context="행복아파트 정문과 1단지 출입구 주변에서 같은 내용이 반복 접수됩니다.",
            entity_texts=["행복아파트", "1단지 출입구", "공사장", "야간 소음", "진동"],
            request_segments=["야간 공사 소음 저감 조치 요청", "작업 시간 안내 요청"],
        ),
    ]

    data = _run_analysis(client, events)

    assert data["count"] == 1
    group = data["duplicate_groups"][0]
    assert group["status"] == "candidate"
    assert group["representative_complaint_id"] == "noise-rich"
    assert set(group["member_complaint_ids"]) == {"noise-basic", "noise-rich"}
    assert group["evidence"]
    assert "confirm" in group["allowed_actions"]
    assert "draft_reply" in group["blocked_actions"]
    assert group["representative"]["selection_reason"]


def test_redaction_placeholders_do_not_inflate_scoring_similarity_or_score() -> None:
    base_left = _scoring_event(
        "placeholder-base-left",
        observation="가로등 점멸 고장 신고입니다.",
        request_text="가로등 점검 요청",
        request_segments=["가로등 점검 요청"],
        entity_texts=["가로등"],
    )
    base_right = _scoring_event(
        "placeholder-base-right",
        observation="복지 급여 지급 일정 문의입니다.",
        request_text="복지 급여 지급 일정 문의",
        request_segments=["복지 급여 지급 일정 문의"],
        entity_texts=["복지급여"],
    )
    redacted_left = _scoring_event(
        "placeholder-redacted-left",
        observation="가로등 점멸 고장 신고입니다. [REDACTED:PHONE]",
        request_text="가로등 점검 요청 [REDACTED:EMAIL]",
        request_segments=["가로등 점검 요청 [REDACTED:PHONE]"],
        entity_texts=["가로등", "[REDACTED:PHONE]"],
        masked_text="[REDACTED:PHONE]",
    )
    redacted_right = _scoring_event(
        "placeholder-redacted-right",
        observation="복지 급여 지급 일정 문의입니다. [REDACTED:PHONE]",
        request_text="복지 급여 지급 일정 문의 [REDACTED:EMAIL]",
        request_segments=["복지 급여 지급 일정 문의 [REDACTED:PHONE]"],
        entity_texts=["복지급여", "[REDACTED:PHONE]"],
        masked_text="[REDACTED:PHONE]",
    )

    base_result = score_duplicate_pair(base_left, base_right)
    redacted_result = score_duplicate_pair(redacted_left, redacted_right)

    assert "[REDACTED:" not in analysis_text(redacted_left)
    assert "[REDACTED:" not in analysis_text(redacted_right)
    assert redacted_result.breakdown["semantic_similarity"] == base_result.breakdown["semantic_similarity"]
    assert redacted_result.breakdown["request_segment_similarity"] == base_result.breakdown["request_segment_similarity"]
    assert redacted_result.score == base_result.score
    assert _duplicate_score_evidence_value(redacted_result) == _duplicate_score_evidence_value(base_result)


def test_same_keywords_different_locations_get_location_mismatch_or_separate_groups() -> None:
    client = TestClient(app)
    events = [
        _event("noise-happy", region="행복아파트", entity_texts=["행복아파트", "공사장", "소음"]),
        _event("noise-blue", region="푸른아파트", entity_texts=["푸른아파트", "공사장", "소음"]),
    ]

    data = _run_analysis(client, events)

    if data["count"] == 0:
        assert data["duplicate_groups"] == []
    else:
        codes = {flag["code"] for flag in data["duplicate_groups"][0]["risk_flags"]}
        assert "LOCATION_MISMATCH" in codes


def test_request_type_mismatch_is_reported_for_same_event_group() -> None:
    client = TestClient(app)
    events = [
        _event(
            "parking-enforcement",
            region="연희초등학교",
            department="교통지도과",
            request_text="불법 주정차 단속 강화 요청",
            observation="연희초등학교 앞 불법 주정차가 반복됩니다.",
            entity_texts=["연희초등학교", "불법주정차"],
        ),
        _event(
            "parking-compensation",
            region="연희초등학교",
            department="교통지도과",
            request_text="불법 주정차 차량으로 인한 차량 파손 피해 보상 요청",
            observation="연희초등학교 앞 같은 위치에서 차량 파손 피해가 발생했습니다.",
            entity_texts=["연희초등학교", "불법주정차"],
        ),
    ]

    data = _run_analysis(client, events)

    group = data["duplicate_groups"][0]
    codes = {flag["code"] for flag in group["risk_flags"]}
    assert "REQUEST_TYPE_MISMATCH" in codes
    assert "LEGAL_RIGHTS_OR_DEADLINE_RISK" in codes


def test_candidate_draft_reply_is_rejected_with_409() -> None:
    client = TestClient(app)
    data = _run_analysis(client, [_event("draft-candidate-1"), _event("draft-candidate-2", minutes_ago=10)])
    merge_id = data["duplicate_groups"][0]["merge_id"]

    response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/draft-reply")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_GROUP_NOT_CONFIRMED"


def test_duplicate_groups_can_be_filtered_by_status_and_complaint_id() -> None:
    client = TestClient(app)
    data = _run_analysis(client, [_event("filter-1"), _event("filter-2", minutes_ago=10)])
    merge_id = data["duplicate_groups"][0]["merge_id"]

    by_complaint = client.get("/complaint-intelligence/duplicate-groups", params={"complaint_id": "filter-1"})
    assert by_complaint.status_code == 200
    assert by_complaint.json()["data"]["count"] == 1

    missing_complaint = client.get("/complaint-intelligence/duplicate-groups", params={"complaint_id": "not-member"})
    assert missing_complaint.status_code == 200
    assert missing_complaint.json()["data"]["count"] == 0

    client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/confirm")
    confirmed = client.get(
        "/complaint-intelligence/duplicate-groups",
        params={"status": "confirmed", "complaint_id": "filter-2"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["duplicate_groups"][0]["status"] == "confirmed"


def test_confirmed_group_returns_pii_safe_draft_reply_payload() -> None:
    client = TestClient(app)
    events = [
        _event(
            "draft-safe-1",
            observation="서울로 123 101동 202호 앞 공사 소음이 반복됩니다. 010-1234-5678로 연락 요청",
            context="행복아파트 같은 위치에서 반복된 민원입니다.",
            body="서울로 123 101동 202호 앞 공사 소음입니다. 010-1234-5678 연락 바랍니다.",
        ),
        _event(
            "draft-safe-2",
            minutes_ago=12,
            observation="서울로 123 주변 공사 소음과 진동이 반복됩니다.",
            context="행복아파트 주변 같은 공사장 관련 민원입니다.",
        ),
    ]
    data = _run_analysis(client, events)
    assert data["count"] == 1
    assert "[REDACTED:" not in analysis_text(ComplaintIntelligenceEvent.model_validate(events[0]))
    merge_id = data["duplicate_groups"][0]["merge_id"]

    confirm_response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/confirm")
    assert confirm_response.status_code == 200
    assert confirm_response.json()["data"]["duplicate_group"]["status"] == "confirmed"

    draft_response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/draft-reply")
    assert draft_response.status_code == 200
    payload = draft_response.json()["data"]["draft_reply_payload"]
    serialized = draft_response.text

    assert payload["merge_id"] == merge_id
    assert payload["representative"]["structured_elements"]
    assert "010-1234-5678" not in serialized
    assert "101동 202호" not in serialized
    assert "[REDACTED:PHONE]" in serialized
    assert "개별 보상" in " ".join(payload["prohibited_content_rules"])


def test_rejected_and_split_groups_cannot_build_draft_reply() -> None:
    client = TestClient(app)
    rejected_data = _run_analysis(client, [_event("reject-1"), _event("reject-2", minutes_ago=5)])
    rejected_id = rejected_data["duplicate_groups"][0]["merge_id"]
    reject_response = client.post(f"/complaint-intelligence/duplicate-groups/{rejected_id}/reject")
    assert reject_response.status_code == 200
    assert reject_response.json()["data"]["duplicate_group"]["status"] == "rejected"
    rejected_draft = client.post(f"/complaint-intelligence/duplicate-groups/{rejected_id}/draft-reply")
    assert rejected_draft.status_code == 409

    service = ComplaintIntelligenceService(repository=InMemoryComplaintIntelligenceRepository())
    set_complaint_intelligence_service(service)
    split_data = _run_analysis(client, [_event("split-1"), _event("split-2", minutes_ago=5)])
    split_id = split_data["duplicate_groups"][0]["merge_id"]
    split_response = client.post(f"/complaint-intelligence/duplicate-groups/{split_id}/split")
    assert split_response.status_code == 200
    assert split_response.json()["data"]["duplicate_group"]["status"] == "split"
    split_draft = client.post(f"/complaint-intelligence/duplicate-groups/{split_id}/draft-reply")
    assert split_draft.status_code == 409


def test_candidate_reply_draft_generation_is_rejected_with_409() -> None:
    client = TestClient(app)
    data = _run_analysis(client, [_event("reply-candidate-1"), _event("reply-candidate-2", minutes_ago=10)])
    merge_id = data["duplicate_groups"][0]["merge_id"]

    response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/reply-draft")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_GROUP_NOT_CONFIRMED"


def test_confirmed_group_reply_draft_uses_generation_pipeline_and_excludes_members(monkeypatch) -> None:
    class FakeRetrievalService:
        async def search(self, **kwargs):
            assert kwargs["exclude_case_id"]
            assert kwargs["request_segments"]
            return [
                {
                    "case_id": "reply-flow-1",
                    "doc_id": "reply-flow-1",
                    "chunk_id": "reply-flow-1__chunk-0",
                    "snippet": "현재 중복 그룹 구성 민원입니다.",
                    "score": 0.99,
                },
                {
                    "case_id": "reply-precedent-1",
                    "doc_id": "reply-precedent-1",
                    "chunk_id": "reply-precedent-1__chunk-0",
                    "snippet": "공사 소음 민원은 현장 확인 후 소음 저감 조치 가능성을 검토합니다.",
                    "score": 0.88,
                },
            ]

    class FakeGenerationService:
        async def generate_qa(self, *, query, context, routing_trace, query_signals):
            assert query
            assert routing_trace["prompt_mode"] == "duplicate_group"
            assert routing_trace["duplicate_group"]["status"] == "confirmed"
            assert all(item.get("case_id") != "reply-flow-1" for item in context)
            assert query_signals["responsible_units_source"] == "duplicate_merge_confirmed_group"
            return {
                "answer": (
                    "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
                    "2. 반복 접수된 공사 소음 사항은 담당자가 확정한 중복 그룹의 공통 검토 대상으로 이해됩니다.\n\n"
                    "3. 담당부서에서 현장 여건과 관련 기준을 확인한 뒤 공통 안내가 가능한 조치와 "
                    "개별 확인이 필요한 사항을 구분해 검토하겠습니다.\n\n"
                    "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 후속 절차를 안내해 드리겠습니다. 감사합니다. 끝."
                ),
                "citations": [
                    {
                        "case_id": "reply-precedent-1",
                        "chunk_id": "reply-precedent-1__chunk-0",
                        "snippet": "공사 소음 민원은 현장 확인 후 소음 저감 조치 가능성을 검토합니다.",
                        "relevance_score": 0.88,
                    }
                ],
                "limitations": ["담당자 검토 후 발송 여부를 결정해야 합니다."],
                "structured_output": {
                    "summary": "공사 소음 반복 민원 공통 답변 초안",
                    "action_items": ["공통 사실관계 확인", "개별 쟁점 분리"],
                    "request_segments": ["공사 소음 저감 조치 요청"],
                    "segment_answers": [],
                },
                "generation_metadata": {"fallback_used": False},
            }

    monkeypatch.setattr("app.complaint_intelligence.service.get_retrieval_service", lambda: FakeRetrievalService())
    monkeypatch.setattr("app.complaint_intelligence.service.get_generation_service", lambda: FakeGenerationService())

    client = TestClient(app)
    data = _run_analysis(client, [_event("reply-flow-1"), _event("reply-flow-2", minutes_ago=10)])
    merge_id = data["duplicate_groups"][0]["merge_id"]
    confirm_response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/confirm")
    assert confirm_response.status_code == 200

    response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/reply-draft")

    assert response.status_code == 200
    reply_draft = response.json()["data"]["reply_draft"]
    assert reply_draft["requires_human_review"] is True
    assert reply_draft["routing_trace"]["prompt_mode"] == "duplicate_group"
    assert reply_draft["generation_metadata"]["duplicate_group_reply"] is True
    assert reply_draft["generation_metadata"]["fallback_used"] is False
    assert all(item["case_id"] != "reply-flow-1" for item in reply_draft["search_results"])
    assert reply_draft["draft_reply_payload"]["merge_id"] == merge_id


def test_reply_draft_falls_back_when_only_duplicate_members_are_retrieved(monkeypatch) -> None:
    class FakeRetrievalService:
        async def search(self, **kwargs):
            return [
                {
                    "case_id": "fallback-flow-1",
                    "doc_id": "fallback-flow-1",
                    "chunk_id": "fallback-flow-1__chunk-0",
                    "snippet": "현재 중복 그룹 구성 민원입니다.",
                    "score": 0.99,
                }
            ]

    class FailIfCalledGenerationService:
        async def generate_qa(self, **kwargs):
            raise AssertionError("검색 근거가 없으면 생성 서비스를 호출하지 않아야 합니다.")

    monkeypatch.setattr("app.complaint_intelligence.service.get_retrieval_service", lambda: FakeRetrievalService())
    monkeypatch.setattr("app.complaint_intelligence.service.get_generation_service", lambda: FailIfCalledGenerationService())

    client = TestClient(app)
    data = _run_analysis(client, [_event("fallback-flow-1"), _event("fallback-flow-2", minutes_ago=10)])
    merge_id = data["duplicate_groups"][0]["merge_id"]
    assert client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/confirm").status_code == 200

    response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/reply-draft")

    assert response.status_code == 200
    reply_draft = response.json()["data"]["reply_draft"]
    assert reply_draft["generation_metadata"]["fallback_used"] is True
    assert "NO_SEARCH_CONTEXT" in reply_draft["safety_warnings"]
    assert reply_draft["citations"] == []
    assert reply_draft["search_results"] == []


def test_reply_draft_falls_back_when_retrieval_fails(monkeypatch) -> None:
    class FailingRetrievalService:
        async def search(self, **kwargs):
            raise RetrievalError("검색 인덱스가 준비되지 않았습니다.")

    class FailIfCalledGenerationService:
        async def generate_qa(self, **kwargs):
            raise AssertionError("검색 실패 시 생성 서비스를 호출하지 않아야 합니다.")

    monkeypatch.setattr("app.complaint_intelligence.service.get_retrieval_service", lambda: FailingRetrievalService())
    monkeypatch.setattr("app.complaint_intelligence.service.get_generation_service", lambda: FailIfCalledGenerationService())

    client = TestClient(app)
    data = _run_analysis(client, [_event("retrieval-fail-1"), _event("retrieval-fail-2", minutes_ago=10)])
    merge_id = data["duplicate_groups"][0]["merge_id"]
    assert client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/confirm").status_code == 200

    response = client.post(f"/complaint-intelligence/duplicate-groups/{merge_id}/reply-draft")

    assert response.status_code == 200
    reply_draft = response.json()["data"]["reply_draft"]
    assert reply_draft["generation_metadata"]["fallback_reason"] == "RETRIEVAL_ERROR"
    assert "RETRIEVAL_ERROR" in reply_draft["safety_warnings"]
    assert reply_draft["requires_human_review"] is True


def test_reply_safety_warns_for_pii_and_prohibited_promises() -> None:
    warnings = build_reply_safety_warnings(
        "010-1234-5678 또는 test@example.com으로 자동 발송하고 보상해 드리겠습니다."
    )

    assert "PII_PHONE" in warnings
    assert "PII_EMAIL" in warnings
    assert "AUTO_SEND_PROMISE" in warnings
    assert "COMPENSATION_PROMISE" in warnings


def test_duplicate_group_prompt_mode_includes_group_safety_rules() -> None:
    prompt = PromptFactory.build(
        query="공사 소음 공통 답변",
        context=[
            {
                "case_id": "reply-precedent-1",
                "chunk_id": "reply-precedent-1__chunk-0",
                "snippet": "공사 소음 민원은 현장 확인 후 안내합니다.",
                "score": 0.8,
            }
        ],
        routing_trace={
            "topic_type": "general",
            "complexity_level": "medium",
            "complexity_score": 0.6,
            "request_segments": ["소음 저감 요청"],
            "retrieval_policy": "general",
            "prompt_mode": "duplicate_group",
            "duplicate_group": {
                "merge_id": "merge-1",
                "representative_complaint_id": "case-1",
                "constraints": ["자동 발송 금지", "개별 보상 판단 금지"],
                "risk_flags": ["LOW_EVIDENCE: 구조화 근거 부족"],
                "evidence": ["같은 위치의 공사 소음"],
                "member_summaries": ["case-2: 같은 공사 소음 민원"],
            },
        },
    )

    assert "[duplicate_group MODE]" in prompt
    assert "[DUPLICATE GROUP CONTEXT]" in prompt
    assert "자동 발송" in prompt
    assert "개별 보상" in prompt

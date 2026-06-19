from __future__ import annotations

import pytest

from app.core.exceptions import NoEvidenceError
from app.generation.normalization.response_normalizer import (
    normalize_response,
    validate_unified_contract,
)
from app.generation.prompts.prompt_factory import PromptFactory


CONTEXT = [
    {
        "doc_id": "DOC-001",
        "chunk_id": "CASE-1__chunk-0",
        "case_id": "CASE-1",
        "score": 0.9,
        "snippet": "버스 배차 간격 민원은 노선 현황 확인 후 담당 부서에서 검토합니다.",
    },
    {
        "doc_id": "DOC-002",
        "chunk_id": "CASE-2__chunk-0",
        "case_id": "CASE-2",
        "score": 0.8,
        "snippet": "현장 확인이 필요한 경우 민원 접수 후 관련 부서 협의를 진행합니다.",
    },
    {
        "doc_id": "DOC-003",
        "chunk_id": "CASE-3__chunk-0",
        "case_id": "CASE-3",
        "score": 0.7,
        "snippet": "추가 자료가 필요한 민원은 처리 한계를 안내하고 보완을 요청합니다.",
    },
]


def _build_prompt(mode: str) -> str:
    return PromptFactory.build(
        query="출퇴근 시간 버스 배차 간격이 길어 불편합니다.",
        context=CONTEXT,
        routing_trace={
            "topic_type": "traffic",
            "complexity_level": "high",
            "retrieval_policy": "field_ops",
            "request_segments": ["배차 간격 단축 요청", "혼잡 시간 현장 확인 요청"],
            "prompt_mode": mode,
        },
    )


@pytest.mark.parametrize("mode", ["default", "compact", "force_json"])
def test_prompt_factory_builds_all_modes_with_schema_and_citation_rules(mode: str):
    prompt = _build_prompt(mode)

    assert f"prompt_mode={mode}" in prompt
    assert "JSON Schema Draft 2020-12" in prompt
    assert '"required":["answer","citations","limitations","structured_output"]' in prompt
    assert "[COMMON JSON RULES]" in prompt
    assert "JSON-only" in prompt
    assert "Required keys must never be omitted" in prompt
    assert "[CITATION RULES]" in prompt
    assert "citations must be selected only from the provided" in prompt
    assert "answer must not contain [[출처 n]]" in prompt
    assert "근거는 citations 배열에만 넣으세요" in prompt
    assert "검색 컨텍스트:" in prompt
    assert "chunk_id=CASE-1__chunk-0" in prompt


def test_prompt_factory_compact_mode_limits_context_and_strengthens_json_only():
    prompt = _build_prompt("compact")

    assert "[compact MODE]" in prompt
    assert "[COMPACT CONTEXT LIMIT]" in prompt
    assert "capped at 2 chunks" in prompt
    assert "Output exactly 1 citation" in prompt
    assert "chunk_id=CASE-1__chunk-0" in prompt
    assert "chunk_id=CASE-2__chunk-0" in prompt
    assert "chunk_id=CASE-3__chunk-0" not in prompt
    assert "stronger JSON-only discipline" in prompt


def test_prompt_factory_force_json_mode_strengthens_required_key_guidance():
    prompt = _build_prompt("force_json")

    assert "[force_json MODE]" in prompt
    assert "Never violate the schema" in prompt
    assert "Prevent required-key omissions" in prompt
    assert "limitations" in prompt


def test_prompt_factory_no_evidence_error_has_actionable_details():
    with pytest.raises(NoEvidenceError) as exc_info:
        PromptFactory.build(
            query="테스트 질문",
            context=[],
            routing_trace={
                "derived_query": "테스트 질문",
                "collection_name": "civil_cases_v1",
                "effective_top_k": 5,
                "filters": {"source": "성남시"},
                "threshold": 0.3,
                "topic_type": "general",
                "complexity_level": "low",
                "route_key": "general:low",
                "strategy_id": "baseline",
                "retrieval_policy": "general",
            },
        )

    err = exc_info.value
    assert "CHROMA_DB_PATH" in str(err)
    assert "collection_name" in str(err)
    assert err.code == "NO_EVIDENCE"
    assert err.details["derived_query"] == "테스트 질문"
    assert err.details["collection_name"] == "civil_cases_v1"
    assert err.details["top_k"] == 5
    assert err.details["effective_top_k"] == 5
    assert err.details["filters"] == {"source": "성남시"}
    assert err.details["threshold"] == 0.3
    assert err.details["routing_trace_summary"]["topic_type"] == "general"
    assert err.details["routing_trace_summary"]["complexity_level"] == "low"
    assert "inspect_chromadb.py count" in " ".join(err.details["hints"]["repro_commands"])


def test_prompt_factory_build_from_dataset_record_extracts_raw_content():
    prompt = PromptFactory.build_from_dataset_record(
        record={
            "source_id": "800806",
            "source": "성남시",
            "consulting_date": "20240521",
            "consulting_category": "대중교통",
            "consulting_turns": "2",
            "consulting_length": 273,
            "consulting_content": (
                "제목 : 야탑역 버스 문제\n\n"
                "Q : 출퇴근 시간에 야탑역에서 버스가 하나밖에 없어 불편합니다.\n"
                "배차 간격을 줄일 수 있는지 검토 바랍니다."
            ),
        },
        context=CONTEXT[:1],
        routing_trace={},
    )

    assert "야탑역 버스 문제" in prompt
    assert "출퇴근 시간에 야탑역" in prompt
    assert "입력 레코드 정보" in prompt
    assert "consulting_category=대중교통" in prompt
    assert "교통/도로 행정 기준" in prompt


def test_prompt_factory_record_trace_passes_title_question_boundary():
    record = {
        "source_id": "ACAS-1",
        "source": "항공",
        "consulting_category": "항공관제",
        "title": "공중충돌경고장치(ACAS/TCAS)가 무엇입니까?",
        "client_question": (
            "○ 공중충돌경고장치란 무엇인가요?\n"
            "○ 공중충돌경고장치의 원리는 무엇입니까?"
        ),
    }
    query = "공중충돌경고장치(ACAS/TCAS)가 무엇입니까?. ○ 공중충돌경고장치란 무엇인가요? ○ 공중충돌경고장치의 원리는 무엇입니까?"

    _query, trace = PromptFactory._derive_query_and_trace(
        record=record,
        query=query,
        routing_trace={},
    )

    assert trace["complexity_trace"]["title_question_boundary_used"] is True
    assert trace["complexity_trace"]["title_duplicate_dropped_count"] == 1
    assert trace["request_segments"] == [
        "○ 공중충돌경고장치란 무엇인가요?",
        "○ 공중충돌경고장치의 원리는 무엇입니까?",
    ]


def test_prompt_factory_treats_raw_query_as_complaint_reply_input():
    raw_query = (
        "제목 : 제2 판교 버스 문제\n\n"
        "Q : 사람이 많이 모이는 역에서 버스가 하나밖에 없어 불편합니다.\n\n"
        "출퇴근 시간 배차간격이 30~40분이고 위험한 상황이 발생합니다.\n"
        "사고가 나기 전에 배차간격을 줄이면 좋겠습니다."
    )

    prompt = PromptFactory.build_from_dataset_record(
        record={
            "case_id": "800806",
            "complaint_id": "800806",
            "query": raw_query,
            "scenario_type": "대중교통과",
        },
        context=CONTEXT[:1],
        routing_trace={},
    )

    assert "질문: 제2 판교 버스 문제. 사람이 많이 모이는 역에서 버스가 하나밖에 없어 불편합니다." in prompt
    assert "민원 원문:" in prompt
    assert raw_query in prompt
    assert "[RAW COMPLAINT REPLY RULES]" in prompt
    assert "write a factual official reply to that complaint" in prompt
    assert "generic context summarizer" in prompt


def test_prompt_factory_search_query_keeps_complaint_body_beyond_first_q_line():
    raw_text = (
        "제목 : 음악실 주말 개방 요청\n\n"
        "Q : 색소폰 동호회 활동을 하고 있습니다.\n"
        "방음된 음악실을 토요일에 사용할 수 있도록 허가해 주세요.\n"
        "주말 개방이 불가능하다면 그 사유와 적용 기준도 안내해 주세요."
    )

    query = PromptFactory._extract_query_from_raw_text(raw_text)

    assert "음악실 주말 개방 요청" in query
    assert "토요일에 사용할 수 있도록 허가" in query
    assert "개방이 불가능하다면" in query


def test_prompt_factory_high_complexity_avoids_internal_answer_labels():
    prompt = _build_prompt("default")

    assert "내부 작업표나 '액션 아이템' 라벨 없이" in prompt
    assert "answer에 '섹션', '액션 아이템' 같은 내부 라벨을 쓰지 마세요" in prompt
    assert prompt.count('"chunk_id":"CASE-1__chunk-0"') == 1


def test_normalize_response_enforces_week6_shape():
    payload = normalize_response(
        {
            "answer": "답변 초안",
            "citations": [{"case_id": "CASE-1", "snippet": "근거 문장"}],
            "limitations": "현장 확인 필요",
        }
    )

    assert isinstance(payload["routing_trace"], dict)
    assert set(payload["structured_output"].keys()) == {"summary", "action_items", "request_segments"}
    assert isinstance(payload["citations"], list)
    assert isinstance(payload["limitations"], list)
    assert set(payload["latency_ms"].keys()) == {"analyzer", "router", "retrieval", "generation"}
    assert set(payload["quality_signals"].keys()) == {
        "citation_coverage",
        "hallucination_flag",
        "segment_coverage",
    }
    assert payload["generation_metadata"] == {
        "fallback_used": False,
        "parse_retry_count": 0,
        "grounding_evidence_count": 0,
        "citation_count": 0,
        "generation_mode": "default",
        "legal_grounding_status": "not_requested",
        "legal_grounding_error": "",
    }


def test_validate_unified_contract_detects_missing():
    missing = validate_unified_contract({"answer": "x"})
    assert "routing_trace" in missing
    assert "structured_output" in missing
    assert "quality_signals" in missing
    assert "generation_metadata" in missing


class _DummyRetrievalService:
    async def search(self, *args, **kwargs):
        return CONTEXT[:2]


class _EmptyRetrievalService:
    async def search(self, *args, **kwargs):
        return []


@pytest.mark.asyncio
async def test_prompt_factory_autoretrieve_builds_prompt_and_context_with_dummy_retrieval():
    prompt, context, trace = await PromptFactory.build_from_dataset_record_autoretrieve(
        record={
            "source_id": "800806",
            "source": "성남시",
            "consulting_category": "대중교통",
            "consulting_content": (
                "제목 : 야탑역 버스 문제\n\n"
                "Q : 출퇴근 시간에 야탑역에서 버스가 하나밖에 없어 불편합니다."
            ),
        },
        routing_trace={},
        retrieval_service=_DummyRetrievalService(),
        top_k=2,
        collection_name="civil_cases_v1",
        filters={"source": "성남시"},
        threshold=0.1,
        mode="compact",
    )

    assert len(context) == 2
    assert context[0]["chunk_id"] == "CASE-1__chunk-0"
    assert "relevance_score" in context[0]
    assert "검색 컨텍스트:" in prompt
    assert "[compact MODE]" in prompt
    assert trace["derived_query"] == "야탑역 버스 문제. 출퇴근 시간에 야탑역에서 버스가 하나밖에 없어 불편합니다."
    assert trace["collection_name"] == "civil_cases_v1"
    assert trace["effective_top_k"] == 2
    assert trace["filters"] == {"source": "성남시"}
    assert trace["threshold"] == 0.1
    assert trace.get("route_key")
    assert trace.get("strategy_id")
    assert trace.get("retrieval_policy")


@pytest.mark.asyncio
async def test_prompt_factory_autoretrieve_raw_query_extracts_derived_query():
    raw_query = (
        "제목 : 제2 판교 버스 문제\n\n"
        "Q : 출퇴근 시간에 특정 방향 버스가 하나밖에 없어 불편합니다.\n"
        "배차간격을 줄여 사고 위험을 낮춰주세요."
    )

    prompt, context, trace = await PromptFactory.build_from_dataset_record_autoretrieve(
        record={
            "case_id": "800806",
            "complaint_id": "800806",
            "query": raw_query,
            "scenario_type": "대중교통과",
        },
        routing_trace={},
        retrieval_service=_DummyRetrievalService(),
        top_k=2,
        collection_name="civil_cases_v1",
        mode="default",
    )

    assert len(context) == 2
    assert trace["derived_query"] == (
        "제2 판교 버스 문제. 출퇴근 시간에 특정 방향 버스가 하나밖에 없어 불편합니다. "
        "배차간격을 줄여 사고 위험을 낮춰주세요."
    )
    assert raw_query in prompt
    assert "[RAW COMPLAINT REPLY RULES]" in prompt


@pytest.mark.asyncio
async def test_prompt_factory_autoretrieve_no_evidence_details_with_dummy_retrieval():
    with pytest.raises(NoEvidenceError) as exc_info:
        await PromptFactory.build_from_dataset_record_autoretrieve(
            record={
                "source_id": "800806",
                "source": "성남시",
                "consulting_category": "대중교통",
                "consulting_content": "제목 : 야탑역 버스 문제\n\nQ : 배차 간격을 줄여주세요.",
            },
            routing_trace={},
            retrieval_service=_EmptyRetrievalService(),
            top_k=2,
            collection_name="civil_cases_v1",
            filters={"source": "성남시"},
            threshold=0.1,
            mode="force_json",
        )

    details = exc_info.value.details
    assert details["context_count"] == 0
    assert details["derived_query"] == "야탑역 버스 문제. 배차 간격을 줄여주세요."
    assert details["collection_name"] == "civil_cases_v1"
    assert details["top_k"] == 2
    assert details["filters"] == {"source": "성남시"}
    assert details["threshold"] == 0.1
    assert details["routing_trace_summary"]["topic_type"] in {
        "traffic",
        "general",
        "welfare",
        "environment",
        "construction",
    }
    assert details["routing_trace_summary"]["strategy_id"]
    assert details["routing_trace_summary"]["retrieval_policy"]

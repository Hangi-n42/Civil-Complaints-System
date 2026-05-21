from __future__ import annotations

import pytest

from app.generation.normalization.response_normalizer import (
    normalize_response,
    validate_unified_contract,
)
from app.generation.prompts.prompt_factory import PromptFactory


def test_prompt_factory_includes_routing_trace_guidance():
    prompt = PromptFactory.build(
        query="임대주택 보수 지연과 관리비 이의제기 관련 민원",
        context=[
            {
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "score": 0.9,
                "snippet": "관리비 이의제기 처리 절차 안내",
            }
        ],
        routing_trace={
            "topic_type": "welfare",
            "complexity_level": "high",
            "request_segments": ["보수 지연", "관리비 이의제기"],
        },
    )

    assert "복지 행정 맥락" in prompt
    assert "다중 쟁점을 분리" in prompt
    assert "섹션 1: 보수 지연" in prompt
    assert "섹션 2: 관리비 이의제기" in prompt

    # 계약 싱크: 단일 JSON 객체 출력 강제 + 핵심 키 존재
    assert "오직 단일 JSON 객체" in prompt
    assert "JSON Schema Draft 2020-12" in prompt
    assert "출력 예시(JSON)" in prompt
    assert "JSON 유효성" in prompt
    assert "trailing comma" in prompt
    assert "NaN/Infinity" in prompt
    assert "[[출처 1]]" in prompt
    assert "코드블록" in prompt
    assert "JSON 객체 외의 다른 텍스트" in prompt
    assert '"answer"' in prompt
    assert '"citations"' in prompt
    assert '"limitations"' in prompt
    assert '"structured_output"' in prompt


def test_prompt_factory_force_json_mode_includes_mode_guidance():
    prompt = PromptFactory.build(
        query="임대주택 보수 지연 관련 민원",
        context=[
            {
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "score": 0.9,
                "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
            }
        ],
        routing_trace={
            "topic_type": "general",
            "complexity_level": "low",
            "prompt_mode": "force_json",
        },
    )

    assert "[force_json 모드]" in prompt


def test_prompt_factory_build_from_dataset_record_extracts_raw_content():
    prompt = PromptFactory.build_from_dataset_record(
        record={
            "source_id": "800806",
            "source": "성남시",
            "consulting_date": "20240521",
            "consulting_category": "대중교통과",
            "consulting_turns": "2",
            "consulting_length": 273,
            "consulting_content": (
                "제목 : 제2 판교 버스 문제\n\n"
                "Q : 사람이 많이 모이는 ▲▲역에서 ▲▲▲▲쪽으로 가는 버스가 ▲▲번 하나밖에 없습니다.\n\n"
                "출퇴근 시간에 해당 버스의 배차간격이 30~40분이고 위험한 상황이 많이 발생합니다.\n"
                "사람이 몰리는 출퇴근 시간에 그 방향 버스가 하나밖에 없는데 사고가 크게 나기 전에 배차간격을 줄이면 좋을 것 같습니다."
            ),
        },
        context=[
            {
                "chunk_id": "CASE-2026-001__chunk-1",
                "case_id": "CASE-2026-001",
                "score": 0.94,
                "snippet": "야간 8시 이후 가로등 소등으로 보행자 전도 위험이 반복 발생한다는 민원이 접수됨.",
            }
        ],
        routing_trace={},
    )

    assert "제2 판교 버스 문제" in prompt
    assert "사람이 많이 모이는 ▲▲역" in prompt
    assert "입력 레코드 정보" in prompt
    assert "consulting_category=대중교통과" in prompt
    assert "교통/도로 행정 기준" in prompt
    assert "교통/도로 행정 기준과 현장 조치 절차" in prompt or "교통/도로 행정 기준" in prompt
    assert "검색 컨텍스트" in prompt


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


def test_validate_unified_contract_detects_missing():
    missing = validate_unified_contract({"answer": "x"})
    assert "routing_trace" in missing
    assert "structured_output" in missing
    assert "quality_signals" in missing


class _DummyRetrievalService:
    async def search(self, *args, **kwargs):
        return [
            {
                "chunk_id": "CASE-2026-001__chunk-1",
                "case_id": "CASE-2026-001",
                "snippet": "야간 8시 이후 가로등 소등으로 보행자 전도 위험이 반복 발생한다는 민원이 접수됨.",
                "score": 0.94,
            },
            {
                "chunk_id": "CASE-2026-019__chunk-2",
                "case_id": "CASE-2026-019",
                "snippet": "교차로 조도 불량 구간에서 차량과 보행자 시야 확보가 어렵다는 신고가 다수 보고됨.",
                "score": 0.88,
            },
        ]


@pytest.mark.asyncio
async def test_prompt_factory_autoretrieve_builds_prompt_and_context():
    prompt, context, trace = await PromptFactory.build_from_dataset_record_autoretrieve(
        record={
            "source_id": "800806",
            "source": "성남시",
            "consulting_date": "20240521",
            "consulting_category": "대중교통과",
            "consulting_turns": "2",
            "consulting_length": 273,
            "consulting_content": (
                "제목 : 제2 판교 버스 문제\n\n"
                "Q : 사람이 많이 모이는 ▲▲역에서 ▲▲▲▲쪽으로 가는 버스가 ▲▲번 하나밖에 없습니다.\n\n"
                "출퇴근 시간에 해당 버스의 배차간격이 30~40분이고 위험한 상황이 많이 발생합니다."
            ),
        },
        routing_trace={},
        retrieval_service=_DummyRetrievalService(),
        top_k=2,
        mode="compact",
    )

    assert isinstance(context, list)
    assert len(context) == 2
    assert context[0]["chunk_id"].startswith("CASE-")
    assert "relevance_score" in context[0]
    assert "검색 컨텍스트" in prompt
    assert "제2 판교 버스 문제" in prompt
    assert trace.get("topic_type") in {"traffic", "general", "welfare", "environment", "construction"}

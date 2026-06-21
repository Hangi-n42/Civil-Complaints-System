from __future__ import annotations

from app.generation.grounding_quality import (
    build_generation_quality_signals,
    rerank_contexts_by_semantic_match,
    sanitize_unsupported_commitments,
)


def test_rerank_contexts_by_semantic_match_promotes_direct_context():
    contexts = [
        {
            "chunk_id": "CASE-OTHER__chunk-0",
            "case_id": "CASE-OTHER",
            "score": 0.99,
            "snippet": "도서관 프로그램 운영 민원에 대한 안내입니다.",
        },
        {
            "chunk_id": "CASE-ROAD__chunk-0",
            "case_id": "CASE-ROAD",
            "score": 0.71,
            "snippet": "포트홀 도로 파손과 차량 안전 위험은 현장 확인 후 보수 가능 여부를 검토합니다.",
        },
    ]

    reranked, trace = rerank_contexts_by_semantic_match(
        contexts,
        query="아파트 진입 도로 포트홀로 차량 파손과 이륜차 전도 위험이 있습니다.",
        request_segments=["도로 포트홀 보수", "차량 안전 위험"],
    )

    assert reranked[0]["chunk_id"] == "CASE-ROAD__chunk-0"
    assert reranked[0]["semantic_match_score"] > 0.0
    assert trace["input_count"] == 2
    assert trace["output_count"] == 1
    assert trace["applied"] is True


def test_quality_signals_detect_commitment_and_segment_gap():
    answer = "3. 검토 의견은 다음과 같습니다. 해당 시설은 다음 주까지 철거하겠습니다."
    sanitized = sanitize_unsupported_commitments(answer)

    assert "철거하겠습니다" not in sanitized
    assert "처리 가능 여부를 검토하겠습니다" in sanitized

    signals = build_generation_quality_signals(
        answer=sanitized,
        citations=[
            {
                "chunk_id": "C1",
                "case_id": "CASE-1",
                "snippet": "시설 철거 요청은 현장 여건과 소관 권한 확인 후 처리 가능 여부를 검토합니다.",
            }
        ],
        contexts=[
            {
                "chunk_id": "C1",
                "case_id": "CASE-1",
                "snippet": "시설 철거 요청은 현장 여건과 소관 권한 확인 후 처리 가능 여부를 검토합니다.",
            }
        ],
        request_segments=["시설 철거 요청", "소음 피해 확인"],
    )

    assert signals["unsupported_commitment_count"] == 0
    assert signals["citation_semantic_support_rate"] > 0.0
    assert signals["segment_coverage_rate"] < 1.0

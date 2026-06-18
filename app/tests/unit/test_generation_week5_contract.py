from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


class _StubGenerationService:
    async def generate_qa(self, query, context, routing_trace=None, query_signals=None):
        return {
            # 내부 generation 결과(모델/파서 산출)는 API unified contract로 그대로 노출되면 안 된다.
            "answer": "요청하신 민원 처리 절차를 안내드립니다.",
            "citations": [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                    "relevance_score": 0.91,
                }
            ],
            "limitations": "실제 처리 기간은 지자체 상황에 따라 달라질 수 있습니다.",
            "structured_output": {
                "summary": "요약: 안전 조치 및 보수 일정 안내",
                "action_items": [
                    "안전 표지판 및 경고 테이프 설치 (즉시)",
                    "현장 조사 및 보수 계획 수립 (3일 이내)",
                ],
                "request_segments": [
                    "모델 임의 세그먼트 1",
                    "모델 임의 세그먼트 2",
                ],
            },
            "confidence": 0.42,
            "question": "임대주택 보수 지연 관련 민원입니다.",
            "model": "stub-model",
            "legal_citations": [
                {
                    "law_name": "건축법",
                    "article_no": "제80조",
                    "law_id": "001823",
                    "public_url": "https://www.law.go.kr/법령/건축법/제80조",
                    "verified": True,
                    "source_url": "http://www.law.go.kr/DRF/lawService.do?OC=secret",
                }
            ],
            "legal_citation_warnings": ["미검증 인용 제거: 건축법 제999조"],
        }


class _StubCitationMapper:
    def validate_citations_against_context(self, citations, retrieval_context):
        return True, 0, []


class _TrackingRetrievalService:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def search(self, query, top_k=5, filters=None, collection_name=None, **kwargs):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "filters": filters,
                "collection_name": collection_name,
                **kwargs,
            }
        )
        return self.results

    async def _apply_grounding_filter(self, query, results, top_k):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "grounding_filter_applied_to_existing_results": True,
            }
        )
        return self.results[:top_k]

    def _normalize_query_signals(self, query_signals):
        return query_signals or {}

    def _apply_metadata_soft_rerank(self, results, query_signals):
        self.calls.append(
            {
                "metadata_soft_rerank": True,
                "query_signals": query_signals,
            }
        )
        return results


class _FailIfCalledGenerationService:
    async def generate_qa(self, query, context, routing_trace=None, query_signals=None):
        raise AssertionError("generation service must not be called for no-evidence fallback")


class _EmptyAnswerGenerationService:
    async def generate_qa(self, query, context, routing_trace=None, query_signals=None):
        return {
            "answer": "   ",
            "citations": [],
            "limitations": "모델 출력 확인이 필요합니다.",
            "generation_metadata": {
                "fallback_used": False,
                "parse_retry_count": 1,
                "generation_mode": "force_json",
            },
        }


class _PrometheusRevisionGenerationService:
    model = "stub-prometheus-model"

    def __init__(self):
        self.prometheus_calls = 0
        self.revision_calls = 0

    async def generate_qa(self, query, context, routing_trace=None, query_signals=None):
        first = context[0]
        return {
            "answer": "검토가 필요합니다.",
            "citations": [
                {
                    "doc_id": first.get("doc_id"),
                    "chunk_id": first.get("chunk_id"),
                    "case_id": first.get("case_id"),
                    "snippet": first.get("snippet"),
                    "relevance_score": 0.91,
                }
            ],
            "limitations": "현장 확인 전 최종 확정은 어렵습니다.",
            "structured_output": {
                "summary": "짧은 초안",
                "action_items": ["검토"],
                "request_segments": [],
            },
            "generation_metadata": {
                "fallback_used": False,
                "parse_retry_count": 0,
                "generation_mode": "default",
            },
        }

    async def call_ollama(self, prompt, temperature=0.0, response_schema=None):
        import json

        if "[PROMETHEUS REVISION TASK]" in prompt:
            self.revision_calls += 1
            return json.dumps(
                {
                    "answer": (
                        "1. 귀하께서 제기하신 도로 파손 및 주변 안전 우려 민원에 대해 답변드립니다.\n\n"
                        "2. 해당 사항은 현장 확인과 소관 부서 검토가 필요한 사안으로 이해됩니다.\n\n"
                        "3. 검토 의견은 다음과 같습니다. 담당부서에서 도로 파손 상태와 통행 안전 위험을 확인하고, "
                        "보수 가능 여부와 필요한 안전조치 범위를 검토하겠습니다. 불법 주정차 관련 사항은 소관 부서와 "
                        "협의하여 단속 또는 계도 가능 여부를 확인하겠습니다.\n\n"
                        "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 후속 절차를 안내드리겠습니다."
                    ),
                    "citations": [
                        {
                            "doc_id": "DOC-001",
                            "chunk_id": "CASE-1__chunk-0",
                            "case_id": "CASE-1",
                            "snippet": "도로 파손과 안전 우려 민원은 현장 확인 후 담당 부서에서 검토합니다.",
                            "relevance_score": 0.91,
                        }
                    ],
                    "limitations": "현장 확인 결과에 따라 처리 방향이 달라질 수 있습니다.",
                    "structured_output": {
                        "summary": "도로 파손 및 주변 안전 우려 민원",
                        "action_items": ["현장 확인", "보수 가능 여부 검토", "소관 부서 협의"],
                        "request_segments": [],
                    },
                },
                ensure_ascii=False,
            )

        self.prometheus_calls += 1
        return json.dumps(
            {
                "feedback": "답변이 지나치게 짧아 민원 요지와 처리 절차가 충분히 드러나지 않습니다.",
                "strengths": ["민원 검토 필요성은 언급했습니다."],
                "weaknesses": ["도로 파손과 안전 우려에 대한 구체적 절차가 부족합니다."],
                "revision_hint": "현장 확인, 소관 부서 검토, 후속 문의 안내를 포함해 공문형 답변으로 보강하세요.",
                "risk_flags": ["too_short"],
            },
            ensure_ascii=False,
        )


def _assert_civil_llm_rubric_attached(data: dict) -> None:
    quality = data["quality_signals"]
    assert quality["civil_llm_rubric_q0"] is not None
    assert quality["civil_llm_rubric_human_review_required"] in {True, False}
    assert quality["civil_llm_rubric_judge_status"] in {
        "rule_fallback",
        "llm_judge",
        "llm_judge_partial_with_rule_fallback",
        "error",
    }

    rubric = data["generation_metadata"]["civil_llm_rubric"]
    assert rubric["rubric_version"] == "civil_llm_rubric_q0_q7_v1.0"
    assert rubric["judge_prompt_version"] == "judge_prompt_2026_06_18"
    assert set(rubric["llm_rubric_raw"].keys()) == {
        "q0",
        "q1",
        "q2",
        "q3",
        "q4",
        "q5",
        "q6",
        "q7",
    }
    assert rubric["safety_layer"]["final_q0_score_0_10"] == quality["civil_llm_rubric_q0"]


def test_qa_requires_routing_hint(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0001",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "top_k": 5,
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "routing_hint is required"


def test_qa_rejects_inconsistent_strategy_and_route_key(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0002",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_traffic_low_v1",
                "route_key": "welfare/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "ROUTING_STRATEGY_INCONSISTENT"


def test_qa_rejects_malformed_route_key(monkeypatch):
    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0003",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high/extra",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "exactly one slash" in body["error"]["message"]


def test_qa_week5_response_skeleton(monkeypatch):
    from app.api.routers import generation as generation_router
    retrieval_service = _TrackingRetrievalService(
        [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                "score": 0.91,
            }
        ]
    )

    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _StubGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0001",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
            "use_search_results": True,
            "search_results": [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                    "score": 0.91,
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "request_id" in body
    assert "timestamp" in body

    data = body["data"]
    assert data["complaint_id"] == "CMP-2026-0001"
    assert data["strategy_id"] == "topic_welfare_high_v1"
    assert data["route_key"] == "welfare/high"
    assert isinstance(data["routing_trace"], dict)
    assert data["routing_trace"]["complexity_level"] in {"low", "medium", "high"}
    assert 0.0 <= float(data["routing_trace"]["complexity_score"]) <= 1.0
    assert isinstance(data["routing_trace"]["route_reason"], str)
    assert data["routing_trace"]["route_reason"]
    assert set(data["structured_output"].keys()) == {"summary", "action_items", "request_segments"}
    assert data["structured_output"]["summary"] == "안전 조치 및 보수 일정 안내"
    assert data["structured_output"]["request_segments"] == ["임대주택 보수 지연 관련 민원입니다."]
    assert data["structured_output"]["action_items"] == [
        "안전 표지판 및 경고 테이프 설치 필요성 및 소관 권한 검토",
        "현장 조사 및 보수 계획 수립 필요성 및 소관 권한 검토",
    ]
    assert isinstance(data["answer"], str)
    assert isinstance(data["citations"], list)
    assert data["legal_citations"][0]["public_url"].endswith("/건축법/제80조")
    assert "source_url" not in data["legal_citations"][0]
    assert data["legal_citation_warnings"] == ["미검증 인용 제거: 건축법 제999조"]
    assert isinstance(data["limitations"], list)
    assert "model" not in data
    assert "confidence" not in data
    assert "question" not in data
    assert set(data["latency_ms"].keys()) == {"analyzer", "router", "retrieval", "generation"}
    assert {
        "citation_coverage",
        "hallucination_flag",
        "segment_coverage",
        "civil_llm_rubric_q0",
        "civil_llm_rubric_human_review_required",
        "civil_llm_rubric_judge_status",
    }.issubset(data["quality_signals"].keys())
    metadata = data["generation_metadata"]
    assert metadata["fallback_used"] is False
    assert metadata["parse_retry_count"] == 0
    assert metadata["grounding_evidence_count"] == 1
    assert metadata["citation_count"] == 1
    assert metadata["generation_mode"] == "default"
    assert metadata["legal_grounding_status"] == "not_requested"
    assert metadata["legal_grounding_error"] == ""
    _assert_civil_llm_rubric_attached(data)
    assert body["qa_validation"]["is_valid"] is True
    assert body["search_trace"]["retrieved_count"] == 1
    assert body["citation_validation"]["is_valid"] is True
    assert data["quality_signals"]["hallucination_flag"] is True


def test_qa_internal_search_enables_grounding_filter(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService(
        [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                "score": 0.91,
            }
        ]
    )

    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _StubGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0005",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high",
                "top_k": 9,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 200
    assert retrieval_service.calls
    assert retrieval_service.calls[0]["grounding_filter"] is True
    assert retrieval_service.calls[0]["top_k"] == 5


def test_qa_reused_search_results_are_filtered_before_generation(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService(
        [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                "score": 0.91,
            }
        ]
    )

    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _StubGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0007",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high",
                "top_k": 9,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
            "use_search_results": True,
            "search_results": [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                    "score": 0.91,
                }
            ],
            "query_signals": {"legal_ref_ids": ["001823"]},
        },
    )

    assert response.status_code == 200
    assert any(call.get("metadata_soft_rerank") for call in retrieval_service.calls)
    grounding_call = next(
        call
        for call in retrieval_service.calls
        if call.get("grounding_filter_applied_to_existing_results")
    )
    assert grounding_call["top_k"] == 5


def test_qa_filtered_search_results_empty_use_no_evidence_fallback(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService([])

    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _FailIfCalledGenerationService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0010",
            "query": "교육 지원 절차와 예약 방법을 알려주세요.",
            "routing_hint": {
                "strategy_id": "topic_general_low_v1",
                "route_key": "general/low",
                "top_k": 5,
                "snippet_max_chars": 1100,
                "chunk_policy": "balanced",
            },
            "use_search_results": True,
            "search_results": [
                {
                    "doc_id": "DOC-BROAD-1",
                    "chunk_id": "CASE-BROAD-1__chunk-0",
                    "case_id": "CASE-BROAD-1",
                    "snippet": "관련성이 낮아 grounding filter에서 제거될 문서입니다.",
                    "score": 0.71,
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"].strip()
    assert data["citations"] == []
    assert data["generation_metadata"]["fallback_used"] is True
    assert data["generation_metadata"]["generation_mode"] == "no_evidence_fallback"
    assert data["generation_metadata"]["grounding_evidence_count"] == 0
    assert data["generation_metadata"]["citation_count"] == 0
    assert "담당부서" in data["answer"]


def test_qa_low_evidence_continues_generation_and_reports_counts(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService(
        [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "교육 지원 신청은 담당 부서 검토를 거칩니다.",
                "score": 0.91,
            },
            {
                "doc_id": "DOC-002",
                "chunk_id": "CASE-2__chunk-0",
                "case_id": "CASE-2",
                "snippet": "예약 절차는 접수 기관 확인이 필요합니다.",
                "score": 0.84,
            },
        ]
    )

    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _StubGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0011",
            "query": "교육 지원 절차와 예약 방법을 알려주세요.",
            "routing_hint": {
                "strategy_id": "topic_general_low_v1",
                "route_key": "general/low",
                "top_k": 5,
                "snippet_max_chars": 1100,
                "chunk_policy": "balanced",
            },
            "use_search_results": True,
            "search_results": retrieval_service.results,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"].strip()
    assert data["generation_metadata"]["fallback_used"] is False
    assert data["generation_metadata"]["generation_mode"] == "default"
    assert data["generation_metadata"]["grounding_evidence_count"] == 2
    assert data["generation_metadata"]["citation_count"] == 1


def test_qa_no_similar_case_fallback_returns_success_without_citations(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService([])

    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _FailIfCalledGenerationService(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0006",
            "query": "가로등 고장으로 야간 보행이 불편합니다.",
            "routing_hint": {
                "strategy_id": "topic_general_low_v1",
                "route_key": "general/low",
                "top_k": 1,
                "snippet_max_chars": 400,
                "chunk_policy": "compact",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["citations"] == []
    assert data["legal_citations"] == []
    assert data["legal_citation_warnings"] == []
    assert data["quality_signals"]["citation_coverage"] == 0.0
    metadata = data["generation_metadata"]
    assert metadata["fallback_used"] is True
    assert metadata["parse_retry_count"] == 0
    assert metadata["grounding_evidence_count"] == 0
    assert metadata["citation_count"] == 0
    assert metadata["generation_mode"] == "no_evidence_fallback"
    assert metadata["legal_grounding_status"] == "not_requested"
    assert metadata["legal_grounding_error"] == ""
    _assert_civil_llm_rubric_attached(data)
    assert "유사 민원 근거가 충분하지 않아" in data["limitations"][0]
    assert "충분히 유사한 사례는 확인되지 않았습니다" in data["answer"]
    assert retrieval_service.calls[0]["grounding_filter"] is True


def test_qa_marks_api_fallback_when_generation_answer_is_empty(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService(
        [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                "score": 0.91,
            }
        ]
    )
    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _EmptyAnswerGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0008",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"].strip()
    metadata = data["generation_metadata"]
    assert metadata["fallback_used"] is True
    assert metadata["parse_retry_count"] == 1
    assert metadata["grounding_evidence_count"] == 1
    assert metadata["citation_count"] == 1
    assert metadata["generation_mode"] == "api_answer_fallback"
    assert metadata["legal_grounding_status"] == "not_requested"
    assert metadata["legal_grounding_error"] == ""
    _assert_civil_llm_rubric_attached(data)
    assert any("API 안전 폴백" in item for item in data["limitations"])


def test_qa_runs_prometheus_feedback_and_revises_low_score_answer(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService(
        [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "도로 파손과 안전 우려 민원은 현장 확인 후 담당 부서에서 검토합니다.",
                "score": 0.91,
            }
        ]
    )
    generation_service = _PrometheusRevisionGenerationService()
    monkeypatch.setattr(
        generation_router.settings,
        "CIVIL_LLM_RUBRIC_USE_LLM_JUDGE",
        False,
    )
    monkeypatch.setattr(
        generation_router.settings,
        "ENABLE_PROMETHEUS_RUBRIC_FEEDBACK",
        True,
    )
    monkeypatch.setattr(
        generation_router.settings,
        "PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE",
        2.0,
    )
    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: generation_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-PROM-1",
            "query": "도로가 파손되어 위험하고 주변 불법 주차도 걱정됩니다.",
            "routing_hint": {
                "strategy_id": "topic_general_high_v1",
                "route_key": "general/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "도로 파손 상태와 통행 안전 위험" in data["answer"]
    assert generation_service.prometheus_calls == 1
    assert generation_service.revision_calls == 1

    revision = data["generation_metadata"]["prometheus_revision"]
    assert revision["attempted"] is True
    assert revision["applied"] is True
    assert revision["trigger_threshold_1_4"] == 2.0
    assert any(item["qid"] == "q7" for item in revision["initial_low_score_items"])

    rubric = data["generation_metadata"]["civil_llm_rubric"]
    assert rubric["prometheus_feedback"]["triggered"] is True
    assert rubric["prometheus_revision"]["applied"] is True


def test_qa_passes_be1_query_signals_to_retrieval_and_generation(monkeypatch):
    from app.api.routers import generation as generation_router

    retrieval_service = _TrackingRetrievalService(
        [
            {
                "doc_id": "DOC-001",
                "chunk_id": "CASE-1__chunk-0",
                "case_id": "CASE-1",
                "snippet": "건축법상 이행강제금 관련 처리 기준을 검토합니다.",
                "score": 0.91,
            }
        ]
    )

    class _TrackingGenerationService(_StubGenerationService):
        def __init__(self):
            self.query_signals = None

        async def generate_qa(
            self,
            query,
            context,
            routing_trace=None,
            query_signals=None,
        ):
            self.query_signals = query_signals
            return await super().generate_qa(
                query,
                context,
                routing_trace=routing_trace,
                query_signals=query_signals,
            )

    generation_service = _TrackingGenerationService()
    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: retrieval_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: generation_service,
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-LEGAL-1",
            "query": "무허가 가설건축물 이행강제금 문의",
            "routing_hint": {
                "strategy_id": "topic_general_high_v1",
                "route_key": "general/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
            "query_signals": {
                "legal_ref_names": ["건축법"],
                "legal_ref_ids": ["001823"],
                "key_terms": ["가설건축물", "이행강제금"],
                "responsible_units": ["건축과"],
                "urgency_level": {"level": "높음"},
            },
        },
    )

    assert response.status_code == 200
    assert retrieval_service.calls[0]["query_signals"]["legal_ref_ids"] == ["001823"]
    assert generation_service.query_signals["legal_ref_ids"] == ["001823"]
    assert generation_service.query_signals["urgency_level"] == "높음"


def test_qa_returns_response_schema_mismatch_when_unified_payload_is_incomplete(monkeypatch):
    from app.api.routers import generation as generation_router

    monkeypatch.setattr(
        generation_router,
        "get_generation_service",
        lambda: _StubGenerationService(),
    )
    monkeypatch.setattr(
        generation_router,
        "get_retrieval_service",
        lambda: _TrackingRetrievalService(
            [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                    "score": 0.91,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        generation_router,
        "get_citation_mapper",
        lambda: _StubCitationMapper(),
    )
    monkeypatch.setattr(
        generation_router,
        "normalize_response",
        lambda payload: {
            key: value
            for key, value in payload.items()
            if key != "structured_output"
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qa",
        json={
            "complaint_id": "CMP-2026-0004",
            "query": "임대주택 보수 지연 관련 민원입니다.",
            "routing_hint": {
                "strategy_id": "topic_welfare_high_v1",
                "route_key": "welfare/high",
                "top_k": 1,
                "snippet_max_chars": 1100,
                "chunk_policy": "expanded",
            },
            "use_search_results": True,
            "search_results": [
                {
                    "doc_id": "DOC-001",
                    "chunk_id": "CASE-1__chunk-0",
                    "case_id": "CASE-1",
                    "snippet": "민원 처리 절차는 접수 후 담당 부서에서 검토합니다.",
                    "score": 0.91,
                }
            ],
        },
    )

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "RESPONSE_SCHEMA_MISMATCH"
    assert "structured_output" in body["error"]["details"]["missing_fields"]

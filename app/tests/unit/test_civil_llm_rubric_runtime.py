from __future__ import annotations

import json

import pytest

from app.evaluation.civil_llm_rubric import CivilComplaintRubricEvaluator
from app.evaluation.prometheus_feedback import select_low_score_items


@pytest.mark.asyncio
async def test_runtime_rubric_runs_rule_fallback_and_applies_missing_citation_cap():
    evaluator = CivilComplaintRubricEvaluator(use_llm_judge=False)

    result = await evaluator.evaluate(
        case_id="CMP-1",
        complaint_text="가로등 고장으로 야간 보행이 불편합니다. 처리 절차를 알려주세요.",
        generated_answer=(
            "1. 귀하의 민원 내용을 확인했습니다.\n\n"
            "3. 검토 의견은 다음과 같습니다. 담당부서에서 현장을 확인하고 처리 절차를 안내드리겠습니다.\n\n"
            "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시기 바랍니다."
        ),
        references=[],
        citations=[],
        citation_validation={"is_valid": False, "mismatch_count": 0},
    )

    assert result["judge_status"] == "rule_fallback"
    assert result["rule_features"]["postprocessed_citation_count"] == 0
    assert result["safety_layer"]["cap_reason"] == "missing_citation"
    assert result["safety_layer"]["final_q0_score_0_10"] <= 4.0
    assert result["diagnostics"]["human_review_required"] is True
    assert set(result["llm_rubric_raw"].keys()) == {
        "q0",
        "q1",
        "q2",
        "q3",
        "q4",
        "q5",
        "q6",
        "q7",
    }


@pytest.mark.asyncio
async def test_runtime_rubric_uses_groups_with_independent_q6_and_q2_reference_only():
    prompts: list[str] = []

    async def fake_llm_call(prompt: str, **kwargs):
        prompts.append(prompt)
        fields = kwargs["response_schema"]["properties"]
        if "choice" in fields:
            return json.dumps({"choice": 4, "confidence": 0.8})
        return json.dumps({qid: {"choice": 4, "confidence": 0.8,
                                "reason": "확인됨", "issues": []} for qid in fields})

    evaluator = CivilComplaintRubricEvaluator(use_llm_judge=True)
    result = await evaluator.evaluate(
        case_id="CMP-2",
        complaint_text="도로 파손과 불법 주차로 위험합니다.",
        generated_answer="검토 의견은 다음과 같습니다. 도로 파손은 현장 확인 후 보수 가능 여부를 안내드립니다.",
        references=[
            {
                "doc_id": "DOC-1",
                "case_id": "CASE-1",
                "title": "도로 보수 처리 기준",
                "snippet": "도로 파손 민원은 현장 확인 후 담당 부서에서 보수 여부를 검토합니다.",
            }
        ],
        citations=[
            {
                "doc_id": "DOC-1",
                "source": "retrieval",
                "quote": "도로 파손 민원은 현장 확인 후 검토합니다.",
            }
        ],
        citation_validation={"is_valid": True, "mismatch_count": 0},
        llm_call=fake_llm_call,
    )

    assert result["judge_status"] == "llm_judge"
    assert len(prompts) == 5
    assert "[생성 답변]" in prompts[3]
    assert "[생성 답변]" not in prompts[0]
    assert result["llm_rubric_raw"]["q0"]["source"] == "llm_judge_synthetic_probs"
    assert result["llm_rubric_raw"]["q0"]["argmax"] == 4
    assert "source=DOC-1" in prompts[1]
    assert "Inline [C1] markers are NOT required" in prompts[1]
    assert "Q4 MUST be 1 or 2" in prompts[1]
    assert "unconfirmed" in prompts[0]
    assert "Ordinary instructions" in prompts[3]


@pytest.mark.asyncio
async def test_routine_guidance_without_law_does_not_force_revision():
    async def judge(prompt, **kwargs):
        fields = kwargs["response_schema"]["properties"]
        item = {"choice": 4, "confidence": 0.9, "reason": "근거와 일치", "issues": []}
        return json.dumps(item if "choice" in fields else {qid: item for qid in fields})

    evaluator = CivilComplaintRubricEvaluator(use_llm_judge=True)
    result = await evaluator.evaluate(
        case_id="routine", complaint_text="누수 신고는 어디에 하나요?",
        generated_answer="누수 위치를 상수도관리팀에 알려 신고해 주세요.",
        references=[{"doc_id": "WATER", "snippet": "누수 위치를 상수도관리팀에 신고합니다."}],
        citations=[{"doc_id": "WATER", "quote": "누수 위치를 상수도관리팀에 신고합니다."}],
        citation_validation={"is_valid": True, "mismatch_count": 0}, llm_call=judge,
    )
    assert not result["safety_layer"]["cap_applied"]
    assert select_low_score_items(result, threshold_1_4=2) == []
    assert "missing_legal_basis" not in json.dumps(result["diagnostics"])
    assert evaluator._manual_core_missing_count({"legal_basis_present": False}) == 0


@pytest.mark.asyncio
async def test_runtime_rubric_semantic_citation_support_affects_q4():
    evaluator = CivilComplaintRubricEvaluator(use_llm_judge=False)

    supported = await evaluator.evaluate(
        case_id="CMP-3",
        complaint_text="The road pothole creates pedestrian safety risk.",
        generated_answer=(
            "The road pothole creates pedestrian safety risk, so the department "
            "should inspect the site and review repair necessity."
        ),
        references=[
            {
                "doc_id": "DOC-ROAD",
                "snippet": (
                    "Road pothole complaints are reviewed through site inspection "
                    "and repair necessity assessment for pedestrian safety."
                ),
            }
        ],
        citations=[
            {
                "doc_id": "DOC-ROAD",
                "snippet": (
                    "Road pothole complaints are reviewed through site inspection "
                    "and repair necessity assessment for pedestrian safety."
                ),
            }
        ],
        citation_validation={"is_valid": True, "mismatch_count": 0},
    )
    unsupported = await evaluator.evaluate(
        case_id="CMP-4",
        complaint_text="The road pothole creates pedestrian safety risk.",
        generated_answer="Music room weekend use can be allocated after schedule coordination.",
        references=[
            {
                "doc_id": "DOC-ROAD",
                "snippet": (
                    "Road pothole complaints are reviewed through site inspection "
                    "and repair necessity assessment for pedestrian safety."
                ),
            }
        ],
        citations=[
            {
                "doc_id": "DOC-ROAD",
                "snippet": (
                    "Road pothole complaints are reviewed through site inspection "
                    "and repair necessity assessment for pedestrian safety."
                ),
            }
        ],
        citation_validation={"is_valid": True, "mismatch_count": 0},
    )

    assert supported["rule_features"]["semantic_citation_support_rate"] > 0
    assert supported["llm_rubric_raw"]["q4"]["score_0_10"] > unsupported["llm_rubric_raw"]["q4"]["score_0_10"]


def test_low_score_items_include_safety_capped_q0_below_six():
    low_items = select_low_score_items(
        {
            "llm_rubric_raw": {
                "q0": {
                    "name": "전체 민원 회신 만족도",
                    "expected_1_4": 3.0,
                    "argmax": 3,
                    "score_0_10": 6.67,
                }
            },
            "safety_layer": {
                "final_q0_score_0_10": 5.0,
                "cap_reason": "special_complaint_process_missing",
            },
        },
        threshold_1_4=2.0,
    )

    assert low_items[0]["qid"] == "q0"
    assert low_items[0]["cap_reason"] == "special_complaint_process_missing"


@pytest.mark.asyncio
async def test_q2_cache_is_request_local_and_invalidated_by_input_changes():
    prompts = []

    async def judge(prompt, **kwargs):
        prompts.append(prompt)
        fields = kwargs['response_schema']['properties']
        value = {'choice': 2, 'confidence': 0.8, 'reason': 'UNIQUE_JUDGE_RESULT', 'issues': []}
        return json.dumps(value if 'choice' in fields else {qid: value for qid in fields})

    evaluator = CivilComplaintRubricEvaluator(use_llm_judge=True)
    inputs = dict(case_id='cache', complaint_text='원문', generated_answer='첫 답변',
                  references=[{'case_id': 'R1', 'snippet': '근거'}], llm_call=judge)
    cache = {}
    first = await evaluator.evaluate(**inputs, q2_cache=cache)
    inputs['generated_answer'] = '수정 답변'
    second = await evaluator.evaluate(**inputs, q2_cache=cache)
    assert len(prompts) == 9
    assert first['llm_rubric_raw']['q2'] == second['llm_rubric_raw']['q2']
    assert all('UNIQUE_JUDGE_RESULT' not in prompt for prompt in prompts)
    assert '첫 답변' not in prompts[0]
    inputs['references'][0]['snippet'] = '변경된 근거'
    await evaluator.evaluate(**inputs, q2_cache=cache)
    assert len(prompts) == 14
    inputs['complaint_text'] = '변경된 원문'
    await evaluator.evaluate(**inputs, q2_cache=cache)
    assert len(prompts) == 19
    await evaluator.evaluate(**inputs, q2_cache={})
    assert len(prompts) == 24


@pytest.mark.asyncio
async def test_group_error_uses_existing_rule_fallback_without_extra_calls():
    calls = []

    async def judge(prompt, **kwargs):
        fields = kwargs['response_schema']['properties']
        calls.append(fields)
        if 'q3' in fields:
            return 'invalid json'
        value = {'choice': 3, 'confidence': 0.8, 'reason': '간단한 사유'}
        return json.dumps(value if 'choice' in fields else {qid: value for qid in fields})

    result = await CivilComplaintRubricEvaluator().evaluate(
        case_id='invalid', complaint_text='민원', generated_answer='답변', llm_call=judge)
    assert len(calls) == 5
    assert result['judge_status'] == 'llm_judge_partial_with_rule_fallback'
    for qid in ('q3', 'q4', 'q5'):
        assert result['llm_rubric_raw'][qid]['source'] == 'rule_fallback_after_llm_error'


@pytest.mark.asyncio
async def test_rubric_transport_separates_model_and_disables_thinking(monkeypatch):
    import httpx
    from app.core.config import settings
    from app.generation.service import GenerationService
    payloads = []

    async def post(client, url, **kwargs):
        payloads.append(kwargs['json'])
        return httpx.Response(200, json={'response': '{"choice":3}'})

    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    service = GenerationService()
    for fields in ({'choice': {}}, {'q3': {}}, {'q1': {}}):
        await service.call_rubric_judge('평가', response_schema={'properties': fields})
    await service.call_ollama('답변 생성')
    assert [p['options']['num_predict'] for p in payloads[:3]] == [192, 1536, 640]
    assert all(p['model'] == settings.CIVIL_LLM_RUBRIC_MODEL and p['think'] is False for p in payloads[:3])
    assert payloads[3]['model'] == settings.OLLAMA_MODEL
    assert 'think' not in payloads[3]
    assert payloads[3]['options']['num_predict'] == settings.GENERATION_NUM_PREDICT


@pytest.mark.parametrize('change,expected', [
    ({}, True),
    ({'support': 'supported'}, False),
    ({'support': 'partial', 'legal_assertion': False}, False),
    ({'support': 'partial', 'legal_assertion': True}, True),
    ({'material': False}, False),
    ({'evidence_id': 'R1'}, False),
    ({'evidence_id': 'C2'}, False),
    ({'sentence': '답변에 없는 문장'}, False),
    ({'excerpt': '근거 없음'}, False),
    ({'excerpt': ''}, False),
])
def test_q4_cap_requires_matching_input_text(change, expected):
    check = dict(sentence='내일 완료됩니다.', evidence_id='C1', excerpt='일정은 미정입니다.',
                 support='contradicted', material=True, legal_assertion=False)
    check.update(change)
    evaluator = CivilComplaintRubricEvaluator()
    assert evaluator._q4_check_can_cap(
        check, '내일 완료됩니다.', [{'doc_id': 'D1', 'snippet': '일정은 미정입니다.'}],
        [{'doc_id': 'D1', 'quote': '일정은 미정입니다.'}],
    ) is expected
    # An excerpt present only in another source must not authorize the cap.
    assert not evaluator._q4_check_can_cap(
        check, '내일 완료됩니다.', [{'doc_id': 'D2', 'snippet': '일정은 미정입니다.'}],
        [{'doc_id': 'D1', 'quote': '일정은 미정입니다.'}],
    )


@pytest.mark.asyncio
async def test_q4_structured_negative_assessment_caps_inconsistent_score():
    async def judge(prompt, **kwargs):
        value = {'choice': 4, 'confidence': 0.9, 'reason': '근거와 반대인 확약', 'issues': []}
        fields = kwargs['response_schema']['properties']
        if 'choice' in fields:
            return json.dumps(value)
        payload = {qid: dict(value) for qid in fields}
        if 'q4' in payload:
            payload['q4']['issues'] = [dict(sentence='내일 완료됩니다.', evidence_id='C1',
                excerpt='모델이 만들어낸 발췌문', support='contradicted', material=True, legal_assertion=False)]
        return json.dumps(payload)

    result = await CivilComplaintRubricEvaluator().evaluate(
        case_id='cap', complaint_text='언제 완료되나요?', generated_answer='내일 완료됩니다.',
        references=[{'doc_id': 'D1', 'snippet': '일정은 미정입니다.'}],
        citations=[{'doc_id': 'D1', 'quote': '일정은 미정입니다.'}], llm_call=judge,
    )
    q4 = result['llm_rubric_raw']['q4']
    assert q4['argmax'] == 2
    detail = json.loads(q4['reason'])
    assert detail['model_choice'] == 4 and detail['consistency_cap_applied'] is True
    assert detail['checks'][0]['excerpt'] == '일정은 미정입니다.'
    assert result['llm_rubric_raw']['q5']['argmax'] == 4

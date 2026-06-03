"""LLM 관련성 필터 스테이지 단위 테스트 (#301). LLM 호출은 mock."""

from __future__ import annotations

import asyncio

from app.evaluation.datasets import EvalQuery
from app.retrieval.pipeline.base import RetrievedDoc, StageInput
from app.retrieval.pipeline.stages.llm_relevance_filter import (
    LLMRelevanceFilterStage,
    _extract_score,
)


def _docs(*docids: str) -> list[RetrievedDoc]:
    return [
        RetrievedDoc(qid="Q1", docid=d, score=float(len(docids) - i), rank=i + 1,
                     stage="rrf_fusion", metadata={"snippet": f"본문 {d}"})
        for i, d in enumerate(docids)
    ]


def _run(stage: LLMRelevanceFilterStage, docs: list[RetrievedDoc]):
    si = StageInput(query=EvalQuery(qid="Q1", text="기준 민원", metadata={}), candidates=docs)
    return asyncio.run(stage.run(si))


def _stage_with_scores(scores: dict[str, int | None], **kw) -> LLMRelevanceFilterStage:
    stage = LLMRelevanceFilterStage(**kw)

    async def fake_score(query_text: str, doc_text: str):  # noqa: ARG001
        for docid, s in scores.items():
            if docid in doc_text:
                return s
        return 0

    stage._score = fake_score  # type: ignore[method-assign]
    return stage


def test_extract_score():
    assert _extract_score('{"score": 2}') == 2
    assert _extract_score("score: 0") == 0
    assert _extract_score("1") == 1
    assert _extract_score("관련 없음") is None
    assert _extract_score("") is None


def test_filters_out_rel0_and_reranks():
    # D1=2, D2=0(제거), D3=1 → 통과 [D1, D3], 점수 desc
    stage = _stage_with_scores({"D1": 2, "D2": 0, "D3": 1}, top_k=5)
    out = _run(stage, _docs("D1", "D2", "D3"))
    assert [d.docid for d in out.candidates] == ["D1", "D3"]
    assert out.metadata == {"scored": 3, "kept": 2}


def test_reranks_by_score_then_original_order():
    # 입력순서 D1,D2,D3 / 점수 D1=1,D2=2,D3=1 → D2 먼저, 동점 D1,D3는 원래순서
    stage = _stage_with_scores({"D1": 1, "D2": 2, "D3": 1}, top_k=5)
    out = _run(stage, _docs("D1", "D2", "D3"))
    assert [d.docid for d in out.candidates] == ["D2", "D1", "D3"]


def test_empty_when_all_rel0():
    # 전부 0점 → 빈 결과(상위에서 "유사 사례 없음" 폴백)
    stage = _stage_with_scores({"D1": 0, "D2": 0}, top_k=5)
    out = _run(stage, _docs("D1", "D2"))
    assert out.candidates == []
    assert out.metadata == {"scored": 2, "kept": 0}


def test_top_k_truncation():
    stage = _stage_with_scores({"D1": 2, "D2": 2, "D3": 1}, top_k=2)
    out = _run(stage, _docs("D1", "D2", "D3"))
    assert len(out.candidates) == 2


def test_rerank_pool_limits_scored_candidates():
    # rerank_pool=2 → 앞 2개만 채점, D3는 아예 후보에서 제외
    stage = _stage_with_scores({"D1": 1, "D2": 1, "D3": 2}, rerank_pool=2, top_k=5)
    out = _run(stage, _docs("D1", "D2", "D3"))
    assert out.metadata["scored"] == 2
    assert "D3" not in [d.docid for d in out.candidates]


def test_llm_failure_is_permissive():
    # 점수 None(LLM 실패) → 제거하지 않고 유지(graceful degradation), 양성 뒤로
    stage = _stage_with_scores({"D1": None, "D2": 2}, top_k=5)
    out = _run(stage, _docs("D1", "D2"))
    assert [d.docid for d in out.candidates] == ["D2", "D1"]


def test_empty_input():
    stage = _stage_with_scores({}, top_k=5)
    out = _run(stage, [])
    assert out.candidates == []


def test_ranks_are_reassigned_sequentially():
    stage = _stage_with_scores({"D1": 2, "D2": 1}, top_k=5)
    out = _run(stage, _docs("D1", "D2"))
    assert [d.rank for d in out.candidates] == [1, 2]

"""Context relevance judge wrapper for ARES-lite."""

from __future__ import annotations

from app.evaluation.ares_lite.evaluator import AresLiteEvaluator, LLMCall
from app.evaluation.ares_lite.schemas import AresLiteCase


class ContextRelevanceJudge:
    def __init__(self, evaluator: AresLiteEvaluator | None = None) -> None:
        self.evaluator = evaluator or AresLiteEvaluator()

    def evaluate(self, case: AresLiteCase) -> dict:
        return self.evaluator.evaluate_context_relevance(case)

    async def evaluate_async(self, case: AresLiteCase, *, llm_call: LLMCall) -> dict:
        return await self.evaluator.evaluate_context_relevance_async(case, llm_call=llm_call)

"""Prompt text references for future optional ARES-lite LLM judges.

The current evaluator is rule-based. These prompt specs document the same
questions used by the deterministic judges so an optional LLM judge can be
added without changing the public output schema.
"""

CONTEXT_RELEVANCE_QUESTION = (
    "검색된 context가 현재 민원의 핵심 이슈, 장소, 시설, 위험 요소, 담당 부서와 "
    "의미적으로 관련 있는가?"
)

ANSWER_FAITHFULNESS_QUESTION = (
    "생성 답변의 사실 주장, 조치 내용, 처리 일정, 담당 부서, 법령 언급이 "
    "검색 context 또는 citation으로 뒷받침되는가?"
)

ANSWER_RELEVANCE_QUESTION = (
    "답변이 민원인의 핵심 요청, 불편 사항, 위험 요소, 조치 요구에 직접 대응하는가?"
)

ARES_LITE_SCORE_GUIDE = {
    "9-10": "핵심 이슈와 직접 관련 있고 근거 또는 답변 대응성이 매우 높음",
    "7-8": "주요 이슈와 관련 있으나 일부 세부 조건은 약함",
    "5-6": "넓은 주제는 같지만 구체성이 부족하거나 일부만 대응함",
    "3-4": "일부 단어만 겹치고 실제 근거 또는 대응성이 약함",
    "0-2": "현재 민원과 거의 무관하거나 답변 근거로 쓰기 어려움",
}

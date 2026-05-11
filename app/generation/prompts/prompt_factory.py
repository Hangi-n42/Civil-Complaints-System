"""Routing-aware PromptFactory for generation stage."""

from __future__ import annotations

from typing import Any, Dict, List


class PromptFactory:
    """routing_trace를 반영해 generation 프롬프트를 구성한다."""

    TOPIC_GUIDANCE = {
        "welfare": "복지 행정 맥락에서 제도/지원 기준과 실제 민원 처리 절차를 분리해 설명하세요.",
        "traffic": "교통/도로 행정 기준과 현장 조치 절차를 분리해 설명하세요.",
        "environment": "환경 민원 처리 절차와 측정/검증 한계를 명확히 안내하세요.",
        "construction": "시설/공사 관련 책임 주체와 조치 순서를 단계별로 제시하세요.",
        "general": "민원 답변 형식(요약-조치-유의사항)을 유지하세요.",
    }

    COMPLEXITY_GUIDANCE = {
        "low": "짧고 명확한 단일 답변으로 작성하세요.",
        "medium": "핵심 쟁점별로 구분하여 작성하세요.",
        "high": "다중 쟁점을 분리하고 단계별 액션 아이템을 구체적으로 작성하세요.",
    }

    @classmethod
    def build(
        cls,
        *,
        query: str,
        context: List[Dict[str, Any]],
        routing_trace: Dict[str, Any],
    ) -> str:
        topic_type = str(routing_trace.get("topic_type") or "general")
        complexity_level = str(routing_trace.get("complexity_level") or "medium")
        request_segments = routing_trace.get("request_segments") or []

        if not isinstance(request_segments, list):
            request_segments = []
        request_segments = [str(item).strip() for item in request_segments if str(item).strip()]

        topic_guide = cls.TOPIC_GUIDANCE.get(topic_type, cls.TOPIC_GUIDANCE["general"])
        complexity_guide = cls.COMPLEXITY_GUIDANCE.get(complexity_level, cls.COMPLEXITY_GUIDANCE["medium"])
        prompt_mode = str(routing_trace.get("prompt_mode") or "default").lower()
        is_compact = prompt_mode == "compact"
        is_force_json = prompt_mode == "force_json"

        segment_guide = ""
        if request_segments:
            numbered = "\n".join(f"- 섹션 {idx + 1}: {segment}" for idx, segment in enumerate(request_segments))
            segment_guide = (
                "\n세그먼트별로 답변을 나누고 각 세그먼트마다 action_items 1개 이상을 붙이세요:\n"
                f"{numbered}"
            )

        snippet_max_chars = 120 if is_compact else 200
        context_limit = 2 if is_compact else len(context)

        context_lines: List[str] = []
        for idx, doc in enumerate(context[:context_limit], start=1):
            snippet = str(doc.get("snippet", "")).strip()
            context_lines.append(
                (
                    f"[{idx}] chunk_id={doc.get('chunk_id', 'unknown')} "
                    f"case_id={doc.get('case_id', 'unknown')} "
                    f"score={doc.get('score', doc.get('relevance_score', 0.0))}\n"
                    f"snippet={snippet[:snippet_max_chars]}"
                )
            )

        if is_compact:
            instruction_block = (
                "설명/주석/마크다운/코드블록(``` 포함) 금지.\n"
                "출력은 반드시 '{' 로 시작하고 '}' 로 끝나야 합니다.\n"
                "JSON 객체 외의 다른 텍스트를 절대 출력하지 마세요.\n"
                "JSON 유효성: 키/문자열은 큰따옴표(\")만 사용, trailing comma(끝 콤마) 금지, NaN/Infinity 금지.\n"
                "answer 형식: 1문장 요약 + 2개 조치 + 1개 유의사항.\n"
                "structured_output.summary 필수, action_items 2개 이상 필수.\n"
                "limitations는 빈 문자열 금지(필요 시 1개 이상 작성).\n"
                "citations는 아래 검색 컨텍스트에서만 선택하고 chunk_id/case_id를 그대로 복사하세요.\n"
                "citations snippet은 answer와 직접 연결되는 근거만 사용(컨텍스트 snippet에서 발췌).\n"
                "answer에는 citations 개수만큼 [[출처 1]] [[출처 2]] ... 토큰을 반드시 포함(문장 끝 권장).\n"
            )
        elif is_force_json:
            instruction_block = (
                "[force_json 모드] JSON만 강제합니다.\n"
                "설명/주석/마크다운/코드블록(``` 포함)은 절대 출력하지 마세요.\n"
                "출력은 반드시 '{' 로 시작하고 '}' 로 끝나야 합니다.\n"
                "JSON 객체 외의 다른 텍스트를 절대 출력하지 마세요.\n"
                "JSON 유효성: 키/문자열은 큰따옴표(\")만 사용, trailing comma(끝 콤마) 금지, NaN/Infinity 금지.\n"
                "아래 JSON Schema의 required 키를 절대 누락하지 마세요.\n"
                "citations는 아래 검색 컨텍스트에서만 선택하고 chunk_id/case_id를 그대로 복사하세요.\n"
                "citations snippet은 컨텍스트 snippet에서 그대로 발췌(빈 문자열 금지).\n"
                "limitations는 빈 문자열 금지(필요 시 1개 이상 작성).\n"
                "answer에는 citations 개수만큼 [[출처 1]] [[출처 2]] ... 토큰을 반드시 포함(문장 끝 권장).\n"
            )
        else:
            instruction_block = (
                "설명/주석/마크다운/코드블록(``` 포함)은 절대 출력하지 마세요.\n"
                "출력은 반드시 '{' 로 시작하고 '}' 로 끝나야 합니다.\n"
                "JSON 객체 외의 다른 텍스트를 절대 출력하지 마세요.\n"
                "JSON 유효성: 키/문자열은 큰따옴표(\")만 사용, trailing comma(끝 콤마) 금지, NaN/Infinity 금지.\n"
                "answer 형식: 1문장 요약 + 2개 조치 + 1개 유의사항.\n"
                "빈 문자열, 템플릿 문구, 근거 반복은 금지합니다.\n"
                "structured_output.summary는 반드시 채우고 action_items는 2개 이상 작성하세요.\n"
                "세그먼트가 있으면 각 세그먼트마다 1개 이상 action_items를 직접 대응시키세요.\n"
                "limitations는 빈 문자열 금지(필요 시 1개 이상 작성).\n"
                "citations는 아래 검색 컨텍스트에서만 선택하고 chunk_id/case_id를 그대로 복사하세요.\n"
                "citations snippet은 answer와 직접 연결되는 근거만 사용(컨텍스트 snippet에서 발췌).\n"
                "answer에는 citations 개수만큼 [[출처 1]] [[출처 2]] ... 토큰을 반드시 포함(문장 끝 권장).\n"
            )

        json_schema = (
            "출력 JSON 스키마(JSON Schema Draft 2020-12):\n"
            "{"
            "\"$schema\":\"https://json-schema.org/draft/2020-12/schema\","
            "\"type\":\"object\","
            "\"additionalProperties\":false,"
            "\"required\":[\"answer\",\"citations\",\"limitations\",\"structured_output\"],"
            "\"properties\":{"
            "\"answer\":{\"type\":\"string\",\"minLength\":1},"
            "\"citations\":{"
            "\"type\":\"array\",\"minItems\":1,\"maxItems\":3,"
            "\"items\":{"
            "\"type\":\"object\",\"additionalProperties\":false,"
            "\"required\":[\"chunk_id\",\"case_id\",\"snippet\",\"relevance_score\"],"
            "\"properties\":{"
            "\"chunk_id\":{\"type\":\"string\",\"minLength\":1},"
            "\"case_id\":{\"type\":\"string\",\"minLength\":1},"
            "\"doc_id\":{\"type\":\"string\"},"
            "\"snippet\":{\"type\":\"string\",\"minLength\":1},"
            "\"relevance_score\":{\"type\":\"number\",\"minimum\":0,\"maximum\":1}"
            "}"
            "}"
            "},"
            "\"limitations\":{"
            "\"oneOf\":["
            "{\"type\":\"string\",\"minLength\":1},"
            "{\"type\":\"array\",\"minItems\":1,\"items\":{\"type\":\"string\",\"minLength\":1}}"
            "]"
            "},"
            "\"structured_output\":{"
            "\"type\":\"object\",\"additionalProperties\":false,"
            "\"required\":[\"summary\",\"action_items\",\"request_segments\"],"
            "\"properties\":{"
            "\"summary\":{\"type\":\"string\",\"minLength\":1},"
            "\"action_items\":{\"type\":\"array\",\"minItems\":2,\"items\":{\"type\":\"string\",\"minLength\":1}},"
            "\"request_segments\":{\"type\":\"array\",\"items\":{\"type\":\"string\"}}"
            "}"
            "}"
            "}"
            "}"
        )

        example_json = (
            "출력 예시(JSON):\n"
            "{"
            "\"answer\":\"요약 1문장. 조치 1. 조치 2. 유의사항 1.\","
            "\"citations\":[{"
            "\"chunk_id\":\"CASE-1__chunk-0\","
            "\"case_id\":\"CASE-1\","
            "\"doc_id\":\"DOC-001\","
            "\"snippet\":\"관리비 이의제기 처리 절차는 접수 후 담당 부서에서 검토합니다.\","
            "\"relevance_score\":0.9"
            "}],"
            "\"limitations\":[\"현장 확인이 필요할 수 있습니다.\"],"
            "\"structured_output\":{"
            "\"summary\":\"핵심 요약\","
            "\"action_items\":[\"조치 1\",\"조치 2\"],"
            "\"request_segments\":[\"세그먼트 1\"]"
            "}"
            "}\n"
        )

        return (
            "검색 기반 QA입니다. 오직 단일 JSON 객체만 출력하세요.\n"
            + json_schema
            + "\n"
            + example_json
            + instruction_block
            + f"도메인 지시문: {topic_guide}\n"
            + f"복잡도 지시문: {complexity_guide}"
            + f"{segment_guide}\n\n"
            + f"질문: {query}\n\n"
            + "검색 컨텍스트:\n"
            + "\n".join(context_lines)
        )

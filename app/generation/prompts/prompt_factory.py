"""Routing-aware PromptFactory for generation stage."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.exceptions import NoEvidenceError
from app.core.logging import pipeline_logger
from app.core.config import settings
from app.retrieval.analyzers.complexity_analyzer import build_analyzer_output
from app.retrieval.analyzers.topic_analyzer import analyze as analyze_topic
from app.retrieval.router.adaptive_router import route
from app.retrieval.service import RetrievalService, get_retrieval_service


class PromptFactory:
    """routing_trace를 반영해 generation 프롬프트를 구성한다."""

    CATEGORY_TOPIC_KEYWORDS = {
        "traffic": (
            "교통",
            "대중교통",
            "도로",
            "주차",
            "주차장",
            "주정차",
            "주차단속",
            "버스",
            "철도",
            "차선",
            "신호",
            "횡단보도",
            "도로표지판",
            "보행",
        ),
        "welfare": ("복지", "보건", "의료", "장애", "노인", "아동", "주거", "지원금"),
        "environment": (
            "환경",
            "하천",
            "기후",
            "에너지",
            "폐기물",
            "쓰레기",
            "재활용",
            "분리수거",
            "소음",
            "악취",
            "매연",
            "침수",
            "홍수",
            "배수",
            "제설",
        ),
        "construction": (
            "건설",
            "공사",
            "시설",
            "시설물",
            "공원",
            "체육",
            "도시정비",
            "안전",
            "조명",
            "보도",
            "계단",
            "일조권",
            "아파트",
            "공동주택",
            "보수",
            "재도색",
            "부실",
        ),
    }

    CATEGORY_POLICY_KEYWORDS = {
        "field_ops": (
            "도로",
            "교통",
            "주차",
            "주정차",
            "신호",
            "소음",
            "악취",
            "매연",
            "침수",
            "제설",
            "안전",
            "공사",
            "시설",
            "조명",
            "보수",
        ),
        "admin_policy": ("복지", "보건", "의료", "지원금", "주거", "행정", "신청", "서류", "예약", "추첨"),
    }

    TOPIC_GUIDANCE = {
        "welfare": "복지 행정 맥락에서 제도/지원 기준과 실제 민원 처리 절차를 분리해, 공문형 민원회신으로 작성하세요.",
        "traffic": "교통/도로 행정 기준과 현장 조치 절차를 분리해, 공문형 민원회신으로 작성하세요.",
        "environment": "환경 민원 처리 절차와 측정/검증 한계를 명확히 하고, 공문형 민원회신으로 작성하세요.",
        "construction": "시설/공사 관련 책임 주체와 조치 순서를 단계별로 제시하되, 공문형 민원회신으로 작성하세요.",
        "general": "요약문이 아니라 공문형 민원회신(1~4항)으로 작성하세요.",
    }

    COMPLEXITY_GUIDANCE = {
        "low": "짧고 명확한 단일 답변으로 작성하세요.",
        "medium": "핵심 쟁점별로 구분하여 작성하세요.",
        "high": "다중 쟁점을 빠짐없이 다루되, answer에는 내부 작업표나 '액션 아이템' 라벨 없이 자연스러운 검토 문장으로 작성하세요.",
    }

    POLICY_GUIDANCE = {
        "field_ops": "현장 대응 관점에서 사실관계·소관 권한·안전 위험을 먼저 확인하고, 확인되지 않은 즉시 조치를 확약하지 마세요.",
        "admin_policy": "행정 절차/근거 중심으로 접수→검토→조치 흐름을 명확히 안내하세요.",
        "general": "현장 대응과 행정 안내를 균형 있게 제시하세요.",
    }

    _TITLE_RE = re.compile(r"^\s*제목\s*[:：]\s*(.+)$", re.MULTILINE)
    _Q_RE = re.compile(r"^\s*Q\s*[:：]\s*(.+)$", re.MULTILINE)
    _ENUM_RE = re.compile(r"^\s*(?:[-*]|\d+[).])\s*(.+)$", re.MULTILINE)

    _KEYWORD_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9_-]{1,30}")
    _KEYWORD_STOPWORDS: set[str] = {
        "민원",
        "요청",
        "불편",
        "발생",
        "확인",
        "필요",
        "조치",
        "관련",
        "안내",
        "검토",
        "가능",
        "현재",
        "지역",
        "주민",
        "시민",
    }

    _SUPPORTED_PROMPT_MODES = {"default", "compact", "force_json"}

    @classmethod
    def _normalize_prompt_mode(cls, mode: str | None) -> str:
        candidate = str(mode or "default").strip().lower() or "default"
        return candidate if candidate in cls._SUPPORTED_PROMPT_MODES else "default"

    @classmethod
    def _build_no_evidence_details(
        cls,
        *,
        routing_trace: Dict[str, Any],
        collection_name: str | None = None,
    ) -> Dict[str, Any]:
        collection = str(
            collection_name
            or routing_trace.get("collection_name")
            or settings.DEFAULT_CHROMA_COLLECTION
        )
        effective_top_k = routing_trace.get("effective_top_k")
        routing_summary = {
            "topic_type": routing_trace.get("topic_type"),
            "complexity_level": routing_trace.get("complexity_level"),
            "route_key": routing_trace.get("route_key"),
            "strategy_id": routing_trace.get("strategy_id"),
            "retrieval_policy": routing_trace.get("retrieval_policy"),
            "prompt_mode": routing_trace.get("prompt_mode"),
        }

        details = {
            **{k: routing_trace.get(k) for k in (
                "derived_query",
                "search_query",
                "keyword_terms",
                "collection_name",
                "effective_top_k",
                "filters",
                "threshold",
                "topic_type",
                "complexity_level",
                "request_segments",
                "route_key",
                "strategy_id",
                "retrieval_policy",
                "prompt_mode",
            )},
            "query": routing_trace.get("derived_query") or routing_trace.get("search_query"),
            "top_k": effective_top_k,
            "routing_trace_summary": routing_summary,
            "context_count": 0,
            "chroma_db_path": str(getattr(settings, "CHROMA_DB_PATH", "")),
            "hints": {
                "checklist": [
                    "Check that CHROMA_DB_PATH points to the populated persist directory.",
                    "Check that collection_name matches an existing Chroma collection.",
                    "Check whether filters, threshold, or top_k are too restrictive.",
                    "Compare derived_query/search_query with the source record to catch query extraction issues.",
                ],
                "repro_commands": [
                    "python scripts/inspect_chromadb.py list",
                    f"python scripts/inspect_chromadb.py count --collection {collection}",
                    f"python scripts/inspect_chromadb.py sample --collection {collection} --limit 3",
                ],
                "api_debug_endpoints": [
                    "GET /api/v1/chroma/collections",
                    f"GET /api/v1/chroma/collections/{collection}/count",
                    f"GET /api/v1/chroma/collections/{collection}/sample?limit=3",
                ],
            },
        }
        details["collection_name"] = collection
        details["effective_top_k"] = effective_top_k
        return details

    @classmethod
    def _raise_no_evidence(cls, *, message: str, routing_trace: Dict[str, Any], collection_name: str | None = None) -> None:
        raise NoEvidenceError(
            message,
            details=cls._build_no_evidence_details(
                routing_trace=routing_trace,
                collection_name=collection_name,
            ),
        )

    @classmethod
    def _build_instruction_block(
        cls,
        *,
        prompt_mode: str,
        citations_max: int,
        context_limit: int,
        snippet_max_chars: int,
        citation_snippet_max_chars: int,
        request_segments: List[str],
        has_raw_complaint: bool = False,
    ) -> str:
        """Build non-conflicting mode rules for schema, citations, and context use."""

        base_json_rules = (
            "[COMMON JSON RULES]\n"
            "- Output exactly one JSON object. JSON-only means no prose, no comments, no Markdown, and no code fences.\n"
            "- The response must start with '{' and end with '}'. Do not emit any text outside the JSON object.\n"
            "- Use double quotes for JSON keys/strings. Do not use trailing commas, NaN, or Infinity.\n"
            "- Follow additionalProperties=false: do not add keys outside the schema.\n"
            "- Top-level keys must be exactly: citations, answer, limitations, structured_output.\n"
            "- Output keys in this exact order so citations are completed before the long answer: citations first, answer second, limitations third, structured_output fourth.\n"
            "- Do not create numbered top-level keys such as \"1\", \"2\", \"3\", and do not use top-level keys such as reply, response, action_items, request_segments, confidence, or routing_trace.\n"
            "- Required keys must never be omitted: answer, citations, limitations, structured_output.\n"
            "- limitations must be non-empty. structured_output.summary must be non-empty.\n"
            "- structured_output.action_items must contain at least 2 items; structured_output.request_segments must be an array.\n"
        )

        citation_rules = (
            "[CITATION RULES]\n"
            "- citations must be selected only from the provided '검색 컨텍스트'. Do not invent external sources.\n"
            f"- Output exactly {citations_max} citation using the single best supporting context chunk.\n"
            "- Every citation must include chunk_id, case_id, snippet, and relevance_score.\n"
            "- Use chunk_id, case_id, score, and relevance_score only inside citations. Never expose these metadata strings inside answer.\n"
            "- Keep all source information in the citations array. The answer must not contain [[출처 n]], [출처 n], chunk_id, case_id, score, or CASE-...__chunk-... strings.\n"
            f"- citation.snippet must be copied from a context snippet, may be a substring, must be non-empty, and must be <= {citation_snippet_max_chars} chars.\n"
            "- citation.relevance_score must use the context score/relevance_score value normalized to 0..1.\n"
            "- The answer must end with the official closing sentence and no source-token lines may follow it.\n"
        )

        complaint_rules = ""
        if has_raw_complaint:
            complaint_rules = (
                "[RAW COMPLAINT REPLY RULES]\n"
                "- Treat '민원 원문' as the citizen's actual request and write a factual official reply to that complaint.\n"
                "- Do not answer as an evaluator, benchmark summarizer, or generic context summarizer.\n"
                "- The answer must be a civil-affairs reply letter, not a retrieval report. Do not start with a meta sentence about checking evidence.\n"
                "- Unless generation fails or a serious uncertainty must be disclosed, answer must use this exact 4-part shell:\n"
                "  1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n"
                "  2. 귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다. 접수된 민원 취지와 관련 근거를 함께 고려하여 처리 방향을 검토하는 사안입니다.\n"
                "  3. 검토 의견은 다음과 같습니다. <write the case-specific reply here>\n"
                "  4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝.\n"
                "- Match the tone of Korean public-agency replies: polite, plain, numbered paragraphs, no Markdown headings, no bullet-heavy action-plan style unless the complaint explicitly asks for a list.\n"
                "- Write enough detail for a real reply: summarize the complaint, explain the applicable review basis, describe possible handling or limits, and give a follow-up/contact path.\n"
                "- Separate the citizen's requested facts, safety concerns, inconvenience, and proposed actions before drafting the answer.\n"
                "- Use '검색 컨텍스트' only as grounding for administrative handling, similar cases, procedures, and limitations.\n"
                "- A retrieved case is a precedent, not a confirmed fact about the current complaint. Do not copy its location, ownership, schedule, decision, or completed action into the current reply.\n"
                "- Statements in the citizen complaint are allegations or requests, not agency-confirmed findings. Attribute them as '민원에서 제기하신 사항' unless independently supported.\n"
                "- Do not write '확인하였습니다' or '보고되었습니다' for facts found only in a retrieved precedent. Use 현장 확인이 필요합니다 unless the current complaint/context proves the fact.\n"
                "- Distinguish requested action from confirmed action. A citizen request such as 설치·철거·보수 요청 is not evidence that the agency approved or performed it.\n"
                "- Preserve decisive constraints found in context, including 처리 불가/곤란, 사유지, 관리사무소·소유자 소관, 도로 폭 부족, 예정 공사, 관할 외 사유, and conditional review.\n"
                "- Do not promise installation, demolition, enforcement, budget allocation, hearings, or a completion schedule unless the context explicitly supports that commitment for the current complaint.\n"
                "- Write from the responding agency's perspective. Do not tell the agency to '검토해 주시기 바랍니다' or present internal action proposals as citizen instructions.\n"
                "- action_items must be evidence-safe. When authority or facts are uncertain, use 확인·협의·안내 actions instead of promising implementation.\n"
                "- If the complaint contains redacted locations such as ▲▲, keep them redacted and do not guess the real place/name.\n"
                "- If the context does not prove a concrete policy, schedule, ordinance, or responsible agency, state that 담당부서 확인/현장 검토가 필요합니다.\n"
                "- Cite a law in answer only when the supplied article text directly supports the stated conclusion. Otherwise omit the law name and article number.\n"
                "- Never output literal \\n text, Markdown bullets, '액션 아이템', 'Action Item', '섹션 n', or an unfinished '[REDACTED:' token inside answer.\n"
            )

        compact_context_rules = ""
        if prompt_mode == "compact":
            compact_context_rules = (
                "[COMPACT CONTEXT LIMIT]\n"
                f"- The provided context is capped at {context_limit} chunks and each snippet is capped at {snippet_max_chars} chars.\n"
                "- Do not assert numbers, dates, ordinances, routes, or agency names that are absent from the context.\n"
            )

        mode_rules: str
        if prompt_mode == "force_json":
            mode_rules = (
                "[force_json MODE]\n"
                "- JSON-only is mandatory. Never violate the schema even when information is uncertain.\n"
                "- Prevent required-key omissions by filling limitations with the missing/uncertain points.\n"
                "- Answer only from the context; if context is insufficient, state the limitation inside limitations.\n"
                "- Keep answer substantive: usually 5 to 8 Korean sentences across 4 numbered paragraphs unless the context is extremely limited.\n"
            )
        elif prompt_mode == "compact":
            mode_rules = (
                "[compact MODE]\n"
                "- Keep answer compact but complete using the exact fixed 1-to-4 paragraph shell and usually 3 to 5 Korean sentences.\n"
                "- Do not use meta phrases about evidence checking; write directly as an institutional reply.\n"
                "- Use stronger JSON-only discipline than default: no Markdown, no headings outside JSON, no explanatory wrapper.\n"
                "- action_items must contain at least 2 prioritized actions.\n"
            )
        else:
            mode_rules = (
                "[default MODE]\n"
                "- Write answer as an official civil-affairs reply, not as a loose summary.\n"
                "- Do not use meta phrases about evidence checking; write directly as an institutional reply.\n"
                "- Recommended answer structure: 1. greeting, 2. complaint summary, 3. review result, 4. next guidance.\n"
                "- Make the answer reasonably detailed: usually 5 to 8 Korean sentences, with at least 2 sentences in the review-result paragraph when context allows.\n"
                "- Facts must come from context. If context lacks a detail, write that it requires confirmation/review.\n"
                "- action_items must contain at least 2 prioritized actions.\n"
            )

        segment_rules = ""
        if request_segments:
            segment_rules = (
                "[REQUEST SEGMENT RULE]\n"
                "- When request_segments are provided, answer each segment and map at least one action_item to each segment.\n"
            )

        return base_json_rules + citation_rules + complaint_rules + compact_context_rules + mode_rules + segment_rules

    @classmethod
    def _extract_keyword_terms(
        cls,
        *,
        record: Dict[str, Any],
        query: str,
        limit: int = 10,
    ) -> List[str]:
        """실데이터 메타 필드 기반으로 검색용 키워드(term)를 추출한다.

        - 목적: ChromaDB 검색(query)에만 보조 키워드를 붙여 recall을 개선
        - 주의: LLM에게 보여주는 질문(query) 자체는 변경하지 않는 것을 전제로 한다.
        """

        candidates: List[str] = []
        for key in (
            "region",
            "source",
            "consulting_category",
            "category",
            "title",
            "summary_request",
            "summary_observation",
        ):
            value = record.get(key)
            if value is None:
                continue
            s = str(value).strip()
            if s:
                candidates.append(s)

        candidates.append(str(query or "").strip())

        seen: set[str] = set()
        terms: List[str] = []
        joined = " ".join(candidates)

        if "REDACTED" in joined:
            joined = joined.replace("REDACTED", "")
        joined = joined.replace("[", " ").replace("]", " ")

        for m in cls._KEYWORD_TOKEN_RE.finditer(joined):
            token = m.group(0).strip()
            if len(token) < 2:
                continue
            if token in cls._KEYWORD_STOPWORDS:
                continue
            if "http" in token.lower():
                continue

            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(token)

            if len(terms) >= int(limit):
                break

        return terms

    @classmethod
    def _build_search_query(cls, *, base_query: str, keyword_terms: List[str], max_chars: int = 650) -> str:
        base = str(base_query or "").strip()
        if not base:
            base = "(빈 질의)"

        parts: List[str] = [base]
        base_lower = base.lower()
        for term in keyword_terms or []:
            t = str(term or "").strip()
            if not t:
                continue
            if t.lower() in base_lower:
                continue
            parts.append(t)

        merged = " ".join(parts).strip()
        if len(merged) > int(max_chars):
            merged = merged[: int(max_chars)].rstrip()
        return merged

    @classmethod
    def _extract_query_from_raw_text(cls, raw_text: str) -> str:
        """원문(consulting_content)에서 검색/라우팅에 유리한 query를 추출한다.

        우선순위:
        1) '제목 :' 라인
        2) Q 본문을 포함한 원문 핵심 구간
        3) fallback: 원문 앞부분
        """
        text = str(raw_text or "").strip()
        if not text:
            return ""

        title_match = cls._TITLE_RE.search(text)
        title = title_match.group(1).strip() if title_match else ""

        body = cls._TITLE_RE.sub(" ", text, count=1)
        body = re.sub(r"(?m)^\s*Q\s*[:：]\s*", "", body)
        body = re.sub(
            r"(?m)^\s*(?:감사합니다|이상[, ]*감사합니다)[.!]?\s*$",
            " ",
            body,
        )
        body = re.sub(r"\s+", " ", body).strip()

        parts = [part for part in (title, body) if part]
        merged = ". ".join(parts)
        return merged[:650].rstrip()

    @classmethod
    def _looks_like_raw_complaint_text(cls, text: str) -> bool:
        """query 필드가 평가 지시문이 아니라 원문 민원 전체인지 판정한다."""
        value = str(text or "").strip()
        if not value:
            return False
        has_title_or_q = bool(cls._TITLE_RE.search(value) or cls._Q_RE.search(value))
        has_multiline_body = value.count("\n") >= 2 and len(value) >= 80
        return has_title_or_q or has_multiline_body

    @classmethod
    def _get_raw_complaint_text(cls, record: Dict[str, Any], query: str = "") -> str:
        """원문 민원 텍스트를 record/query에서 찾는다."""
        raw_text = str(
            record.get("consulting_content")
            or record.get("raw_text")
            or record.get("text")
            or ""
        ).strip()
        if raw_text:
            return raw_text

        for candidate in (record.get("query"), query):
            query_text = str(candidate or "").strip()
            if cls._looks_like_raw_complaint_text(query_text):
                return query_text
        return ""

    @classmethod
    def _derive_query_from_record(cls, record: Dict[str, Any]) -> str:
        """record가 평가 query 또는 원문 민원 중 무엇을 담든 일관된 질의를 만든다."""
        query = str(record.get("query") or "").strip()
        if query and not cls._looks_like_raw_complaint_text(query):
            return query

        raw_text = cls._get_raw_complaint_text(record, query=query)
        if raw_text:
            return cls._extract_query_from_raw_text(raw_text)
        return query

    @classmethod
    def _extract_title_question_boundary(cls, record: Dict[str, Any]) -> Tuple[str, str]:
        """record에 이미 분리된 제목/민원인 원문 경계가 있으면 반환한다."""
        data = record.get("resultData") if isinstance(record.get("resultData"), dict) else record
        if not isinstance(data, dict):
            return "", ""

        title = str(data.get("title") or data.get("qnaTitl") or "").strip()
        question = str(
            data.get("client_question")
            or data.get("qstnCntnCl")
            or data.get("question")
            or ""
        ).strip()
        if title or question:
            return title, question

        raw_text = str(
            data.get("consulting_content")
            or data.get("raw_text")
            or data.get("text")
            or ""
        ).strip()
        if not raw_text:
            return "", ""

        title_match = cls._TITLE_RE.search(raw_text)
        q_blocks = [match.group(1).strip() for match in cls._Q_RE.finditer(raw_text) if match.group(1).strip()]
        return (
            title_match.group(1).strip() if title_match else "",
            "\n".join(q_blocks),
        )

    @classmethod
    def _extract_request_segments_from_raw_text(cls, raw_text: str) -> List[str]:
        """원문에서 다중 요청 단위를 추출한다."""
        text = str(raw_text or "").strip()
        if not text:
            return []

        segments: List[str] = []
        for match in cls._ENUM_RE.finditer(text):
            segment = match.group(1).strip()
            if segment:
                segments.append(segment)

        if segments:
            return segments[:5]

        q_blocks = [m.group(1).strip() for m in cls._Q_RE.finditer(text) if m.group(1).strip()]
        if len(q_blocks) > 1:
            return q_blocks[:5]

        title = cls._TITLE_RE.search(text)
        if title:
            return [title.group(1).strip()]

        return []

    @classmethod
    def _infer_topic_type_from_record(cls, record: Dict[str, Any], fallback: str = "general") -> str:
        """원문 메타데이터를 기반으로 topic_type을 보정한다."""
        candidates = [
            str(record.get("consulting_category") or ""),
            str(record.get("category") or ""),
            str(record.get("source") or ""),
            str(record.get("consulting_content") or record.get("raw_text") or record.get("text") or ""),
        ]

        haystack = " ".join(candidate.lower() for candidate in candidates if candidate).strip()
        if not haystack:
            return fallback

        for topic_type, keywords in cls.CATEGORY_TOPIC_KEYWORDS.items():
            if any(keyword.lower() in haystack for keyword in keywords):
                return topic_type

        return fallback

    @classmethod
    def _infer_retrieval_policy_from_record(cls, record: Dict[str, Any], fallback: str = "general") -> str:
        """원문 메타데이터를 기반으로 retrieval_policy를 보정한다."""
        topic_type = cls._infer_topic_type_from_record(record, fallback="general")
        if topic_type in {"traffic", "environment", "construction"}:
            return "field_ops"

        candidates = [
            str(record.get("consulting_category") or ""),
            str(record.get("consulting_content") or record.get("raw_text") or record.get("text") or ""),
        ]
        haystack = " ".join(candidate.lower() for candidate in candidates if candidate).strip()
        for policy, keywords in cls.CATEGORY_POLICY_KEYWORDS.items():
            if any(keyword.lower() in haystack for keyword in keywords):
                return policy

        return fallback

    @classmethod
    def _infer_complexity_level_from_record(cls, record: Dict[str, Any], fallback: str = "medium") -> str:
        """원문 메타데이터를 기반으로 complexity_level을 보정한다."""
        if str(record.get("requires_multi_request") or "").lower() in {"true", "1", "yes"}:
            return "high"

        content = str(record.get("consulting_content") or record.get("raw_text") or record.get("text") or "")
        if len(cls._extract_request_segments_from_raw_text(content)) >= 2:
            return "high"

        turn_count = str(record.get("consulting_turns") or "").strip()
        if turn_count.isdigit() and int(turn_count) >= 3:
            return "high"

        if len(content) >= 260:
            return "medium"

        return fallback

    @classmethod
    def _build_record_guide(cls, record: Dict[str, Any]) -> str:
        """원문 레코드의 구조화 가능한 메타데이터를 프롬프트에 반영한다."""
        metadata_items = []
        for key in ("source_id", "source", "consulting_date", "consulting_category", "consulting_turns", "consulting_length"):
            value = str(record.get(key) or "").strip()
            if value:
                metadata_items.append(f"- {key}={value}")

        if not metadata_items:
            return ""

        return "\n입력 레코드 정보:\n" + "\n".join(metadata_items)

    @classmethod
    def build_from_dataset_record(
        cls,
        *,
        record: Dict[str, Any],
        context: List[Dict[str, Any]],
        routing_trace: Dict[str, Any],
    ) -> str:
        """evaluation_set 형태가 아니라 원문 레코드(예: 성남시_test_10)에서도 prompt를 구성한다."""
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        query = cls._derive_query_from_record(record)
        if not query:
            query = "(빈 질의)"

        derived_trace = dict(routing_trace or {})
        query, derived_trace = cls._derive_query_and_trace(
            record=record,
            query=query,
            routing_trace=derived_trace,
        )

        request_segments = cls._extract_request_segments_from_raw_text(
            cls._get_raw_complaint_text(record, query=query)
        )
        if request_segments and not derived_trace.get("request_segments"):
            derived_trace["request_segments"] = request_segments

        return cls.build(query=query, context=context, routing_trace=derived_trace, record=record)

    @classmethod
    async def build_from_dataset_record_autoretrieve(
        cls,
        *,
        record: Dict[str, Any],
        routing_trace: Dict[str, Any] | None = None,
        retrieval_service: RetrievalService | None = None,
        top_k: Optional[int] = None,
        collection_name: str = settings.DEFAULT_CHROMA_COLLECTION,
        filters: Optional[Dict[str, Any]] = None,
        threshold: float = 0.0,
        mode: str = "default",
        query_signals: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """원문 레코드만으로 prompt(+검색 컨텍스트)를 만든다.

        - query가 없으면 consulting_content/raw_text/text에서 자동 추출
        - routing_trace가 비어있으면 topic/complexity를 분석해 adaptive routing 적용
        - ChromaDB(/data/chroma_db)에서 근거 청크를 검색해 context를 구성

        Returns:
            (prompt, context, derived_trace)
        """
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        base_trace = dict(routing_trace or {})
        if mode == "force_json":
            base_trace["prompt_mode"] = "force_json"
        elif mode == "compact":
            base_trace["prompt_mode"] = "compact"

        query = cls._derive_query_from_record(record)
        if not query:
            query = "(빈 질의)"

        query, derived_trace = cls._derive_query_and_trace(
            record=record,
            query=query,
            routing_trace=base_trace,
        )

        derived_trace.setdefault("chroma_db_path", str(getattr(settings, "CHROMA_DB_PATH", "")))
        pipeline_logger.info(
            "autoretrieve start: derived_query=%s mode=%s",
            str(derived_trace.get("derived_query") or query),
            str(derived_trace.get("prompt_mode") or "default"),
        )

        keyword_terms = cls._extract_keyword_terms(record=record, query=query, limit=10)
        derived_trace.setdefault("keyword_terms", keyword_terms)
        search_query = cls._build_search_query(base_query=query, keyword_terms=keyword_terms)
        derived_trace.setdefault("search_query", search_query)

        decision = route(
            topic_type=str(derived_trace.get("topic_type") or "general"),
            complexity_level=str(derived_trace.get("complexity_level") or "medium"),
            complexity_score=float(derived_trace.get("complexity_score") or 0.5),
        )
        derived_trace.setdefault("route_key", decision.route_key)
        derived_trace.setdefault("strategy_id", decision.strategy_id)
        derived_trace.setdefault("route_reason", decision.route_reason)
        derived_trace.setdefault("retrieval_policy", decision.retrieval_policy)

        effective_top_k = int(top_k or decision.applied_params.top_k)
        derived_trace.setdefault("collection_name", str(collection_name))
        derived_trace.setdefault("effective_top_k", effective_top_k)
        derived_trace.setdefault("filters", filters or {})
        derived_trace.setdefault("threshold", float(threshold or 0.0))
        exclude_case_id = next(
            (
                str(record.get(key) or "").strip()
                for key in ("case_id", "complaint_id", "source_id")
                if str(record.get(key) or "").strip()
            ),
            "",
        )
        if exclude_case_id:
            derived_trace.setdefault("excluded_case_id", exclude_case_id)

        prompt_mode = str(derived_trace.get("prompt_mode") or "default").lower()
        snippet_max_chars = 120 if prompt_mode == "compact" else 200

        service = retrieval_service or get_retrieval_service()
        raw_context = await service.search(
            query=search_query,
            top_k=effective_top_k,
            threshold=float(threshold or 0.0),
            filters=filters or {},
            collection_name=collection_name,
            topic_type=str(derived_trace.get("topic_type") or "general"),
            request_segments=list(derived_trace.get("request_segments") or []),
            retrieval_policy=str(derived_trace.get("retrieval_policy") or decision.retrieval_policy),
            snippet_max_chars=int(snippet_max_chars),
            query_signals=query_signals,
            grounding_filter=True,
            grounding_pool=max(3, effective_top_k),
            exclude_case_id=exclude_case_id or None,
        )

        pipeline_logger.info(
            "autoretrieve search_done: derived_query=%s search_query=%s context_count=%s collection=%s top_k=%s",
            str(derived_trace.get("derived_query") or ""),
            str(derived_trace.get("search_query") or ""),
            str(len(raw_context) if isinstance(raw_context, list) else 0),
            str(collection_name),
            str(effective_top_k),
        )

        context: List[Dict[str, Any]] = []
        for item in raw_context:
            if not isinstance(item, dict):
                continue
            score = float(item.get("score", item.get("relevance_score", 0.0)) or 0.0)
            normalized = dict(item)
            normalized.setdefault("relevance_score", score)
            context.append(normalized)

        if not context:
            cls._raise_no_evidence(
                message=(
                    "검색 근거가 0개라 프롬프트를 구성할 수 없습니다. "
                    "CHROMA_DB_PATH/collection_name을 확인하거나 top_k/threshold/filters를 조정하세요. "
                    "(inspect_chromadb 또는 /api/v1/chroma 디버그 엔드포인트로 즉시 점검 가능)"
                ),
                routing_trace=derived_trace,
                collection_name=str(collection_name),
            )

        prompt = cls.build_from_dataset_record(record=record, context=context, routing_trace=derived_trace)
        return prompt, context, derived_trace

    @classmethod
    def _derive_query_and_trace(
        cls,
        *,
        record: Dict[str, Any],
        query: str,
        routing_trace: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """query/record를 기반으로 routing_trace 기본값을 채운다."""

        derived_trace = dict(routing_trace or {})
        if query:
            derived_trace.setdefault("derived_query", query)

        raw_text = str(
            record.get("consulting_content")
            or record.get("raw_text")
            or record.get("text")
            or ""
        )
        category_hint = str(record.get("consulting_category") or record.get("category") or "")
        topic_text = "\n".join(part for part in (query, category_hint, raw_text) if str(part).strip())

        topic_type = str(derived_trace.get("topic_type") or "").strip().lower()
        if not topic_type:
            try:
                topic_type = str(analyze_topic(topic_text).topic_type)
            except Exception:
                topic_type = cls._infer_topic_type_from_record(record, fallback="general")
            derived_trace["topic_type"] = topic_type or "general"

        complexity_level = str(derived_trace.get("complexity_level") or "").strip().lower()
        if not complexity_level or "complexity_score" not in derived_trace or "request_segments" not in derived_trace:
            try:
                title, question = cls._extract_title_question_boundary(record)
                analysis = build_analyzer_output(
                    query,
                    topic_type=topic_type or "general",
                    title=title or None,
                    question=question or None,
                )
                derived_trace.setdefault("complexity_level", str(analysis.get("complexity_level") or "medium"))
                derived_trace.setdefault("complexity_score", float(analysis.get("complexity_score") or 0.5))
                request_segments = analysis.get("request_segments")
                if isinstance(request_segments, list) and request_segments:
                    derived_trace.setdefault("request_segments", request_segments[:5])
                complexity_trace = analysis.get("complexity_trace")
                if isinstance(complexity_trace, dict):
                    derived_trace.setdefault("complexity_trace", complexity_trace)
            except Exception:
                derived_trace.setdefault(
                    "complexity_level",
                    cls._infer_complexity_level_from_record(record, fallback=str(derived_trace.get("complexity_level") or "medium")),
                )

        if "retrieval_policy" not in derived_trace:
            try:
                decision = route(
                    topic_type=str(derived_trace.get("topic_type") or "general"),
                    complexity_level=str(derived_trace.get("complexity_level") or "medium"),
                    complexity_score=float(derived_trace.get("complexity_score") or 0.5),
                )
                derived_trace["retrieval_policy"] = decision.retrieval_policy
            except Exception:
                derived_trace["retrieval_policy"] = cls._infer_retrieval_policy_from_record(record, fallback="general")

        return query, derived_trace

    @classmethod
    def build(
        cls,
        *,
        query: str,
        context: List[Dict[str, Any]],
        routing_trace: Dict[str, Any],
        record: Dict[str, Any] | None = None,
    ) -> str:
        topic_type = str(routing_trace.get("topic_type") or "general")
        complexity_level = str(routing_trace.get("complexity_level") or "medium")
        request_segments = routing_trace.get("request_segments") or []
        retrieval_policy = str(routing_trace.get("retrieval_policy") or "general")

        if not context:
            cls._raise_no_evidence(
                message=(
                    "근거 컨텍스트가 0개입니다. 근거 없이 답변을 생성하지 않도록 즉시 실패 처리합니다. "
                    "CHROMA_DB_PATH/collection_name 및 검색 조건(top_k/threshold/filters)을 점검하세요."
                ),
                routing_trace={
                    **dict(routing_trace or {}),
                    "topic_type": topic_type,
                    "complexity_level": complexity_level,
                    "request_segments": request_segments,
                    "retrieval_policy": retrieval_policy,
                    "prompt_mode": routing_trace.get("prompt_mode"),
                },
            )

        if not isinstance(request_segments, list):
            request_segments = []
        request_segments = [str(item).strip() for item in request_segments if str(item).strip()]

        topic_guide = cls.TOPIC_GUIDANCE.get(topic_type, cls.TOPIC_GUIDANCE["general"])
        complexity_guide = cls.COMPLEXITY_GUIDANCE.get(complexity_level, cls.COMPLEXITY_GUIDANCE["medium"])
        policy_guide = cls.POLICY_GUIDANCE.get(retrieval_policy, cls.POLICY_GUIDANCE["general"])
        prompt_mode = cls._normalize_prompt_mode(str(routing_trace.get("prompt_mode") or "default"))
        is_compact = prompt_mode == "compact"
        record_guide = cls._build_record_guide(record or {}) if record else ""
        raw_complaint_text = cls._get_raw_complaint_text(record or {}, query=query) if record else ""
        has_raw_complaint = bool(raw_complaint_text)

        segment_guide = ""
        if request_segments:
            numbered = "\n".join(f"- 요청 {idx + 1}: {segment}" for idx, segment in enumerate(request_segments))
            segment_guide = (
                "\n다음 요청을 빠짐없이 검토하되 answer에 '섹션', '액션 아이템' 같은 내부 라벨을 쓰지 마세요. "
                "structured_output.action_items에는 각 요청과 연결되는 안전한 확인·협의·안내 조치를 넣으세요:\n"
                f"{numbered}"
            )

        snippet_max_chars = 120 if is_compact else 200
        citation_snippet_max_chars = 120 if is_compact else 200
        context_limit = 2 if is_compact else min(3, len(context))
        citations_max = 1

        context_lines: List[str] = []
        for idx, doc in enumerate(context[:context_limit], start=1):
            snippet = str(doc.get("snippet", "")).strip()
            context_lines.append(
                (
                    f"[유사 사례 {idx} - 현재 민원의 확정 사실이 아님] "
                    f"chunk_id={doc.get('chunk_id', 'unknown')} "
                    f"case_id={doc.get('case_id', 'unknown')} "
                    f"score={doc.get('score', doc.get('relevance_score', 0.0))}\n"
                    f"snippet={snippet[:snippet_max_chars]}"
                )
            )

        instruction_block = cls._build_instruction_block(
            prompt_mode=prompt_mode,
            citations_max=citations_max,
            context_limit=context_limit,
            snippet_max_chars=snippet_max_chars,
            citation_snippet_max_chars=citation_snippet_max_chars,
            request_segments=request_segments,
            has_raw_complaint=has_raw_complaint,
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
            f"\"type\":\"array\",\"minItems\":1,\"maxItems\":{citations_max},"
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
            "반드시 아래와 같은 최상위 구조만 사용하세요. reply 또는 번호 키를 만들지 마세요.\n"
            "출력 예시(JSON):\n"
            "{"
            "\"citations\":[{"
            "\"chunk_id\":\"CASE-1__chunk-0\","
            "\"case_id\":\"CASE-1\","
            "\"doc_id\":\"DOC-001\","
            "\"snippet\":\"관리비 이의제기 처리 절차는 접수 후 담당 부서에서 검토합니다.\","
            "\"relevance_score\":0.9"
            "}],"
            "\"answer\":\"1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\\n\\n2. 귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다. 접수된 민원 취지와 관련 근거를 함께 고려하여 처리 방향을 검토하는 사안입니다.\\n\\n3. 검토 의견은 다음과 같습니다. 접수하신 사항은 관리비 이의제기 처리 절차와 현장 확인이 필요한 사항으로 구분하여 검토할 수 있습니다. 담당부서에서는 접수 자료를 확인한 뒤 필요한 경우 관계 부서 협의 또는 현장 확인을 거쳐 처리 가능 여부와 후속 절차를 안내드리겠습니다.\\n\\n4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝.\","
            "\"limitations\":[\"현장 확인이 필요할 수 있습니다.\"],"
            "\"structured_output\":{"
            "\"summary\":\"핵심 요약\","
            "\"action_items\":[\"조치 1\",\"조치 2\"],"
            "\"request_segments\":[\"세그먼트 1\"]"
            "}"
            "}\n"
        )

        return (
            f"검색 기반 QA입니다. prompt_mode={prompt_mode}. 오직 단일 JSON 객체만 출력하세요.\n"
            + json_schema
            + "\n"
            + example_json
            + instruction_block
            + f"도메인 지시문: {topic_guide}\n"
            + f"복잡도 지시문: {complexity_guide}"
            + f"\n운영 정책 지시문: {policy_guide}"
            + record_guide
            + f"{segment_guide}\n\n"
            + "최종 점검: 출력 직전에 최상위 키가 citations/answer/limitations/structured_output 네 개뿐인지 확인하고, citations 키를 가장 먼저 출력하세요. "
            + "answer는 반드시 '1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.'로 시작하고, "
            + "answer는 '감사합니다. 끝.'으로 마치며 그 뒤에 출처 토큰이나 다른 문장을 쓰지 마세요. "
            + "민원인의 요청을 승인·완료된 조치처럼 바꾸지 말고, 유사 사례의 장소·일정·처리 결과를 현재 민원 사실로 옮기지 마세요. "
            + "근거는 citations 배열에만 넣으세요.\n\n"
            + f"질문: {query}\n\n"
            + (f"민원 원문:\n{raw_complaint_text[:1800]}\n\n" if has_raw_complaint else "")
            + "검색 컨텍스트:\n"
            + "\n".join(context_lines)
        )

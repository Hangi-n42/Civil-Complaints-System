"""Routing-aware PromptFactory for generation stage."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.exceptions import NoEvidenceError
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
        "high": "다중 쟁점을 분리하고 단계별 액션 아이템을 구체적으로 작성하세요.",
    }

    POLICY_GUIDANCE = {
        "field_ops": "현장 대응 관점에서 긴급도 판단 근거와 즉시 조치를 우선 제시하세요.",
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
        2) 'Q :' 라인(1개 이상이면 연결)
        3) fallback: 원문 앞부분
        """
        text = str(raw_text or "").strip()
        if not text:
            return ""

        title_match = cls._TITLE_RE.search(text)
        title = title_match.group(1).strip() if title_match else ""

        questions = [m.group(1).strip() for m in cls._Q_RE.finditer(text) if m.group(1).strip()]
        question = " ".join(questions).strip()

        if title and question:
            return f"{title}. {question}".strip()
        if question:
            return question
        if title:
            return title

        fallback = re.sub(r"\s+", " ", text)
        return fallback[:500].strip()

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

        query = str(record.get("query") or "").strip()
        if not query:
            raw_text = (
                record.get("consulting_content")
                or record.get("raw_text")
                or record.get("text")
                or ""
            )
            query = cls._extract_query_from_raw_text(str(raw_text))

        if not query:
            query = "(빈 질의)"

        derived_trace = dict(routing_trace or {})
        query, derived_trace = cls._derive_query_and_trace(
            record=record,
            query=query,
            routing_trace=derived_trace,
        )

        request_segments = cls._extract_request_segments_from_raw_text(
            str(record.get("consulting_content") or record.get("raw_text") or record.get("text") or "")
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
        collection_name: str = "civil_cases_v1",
        filters: Optional[Dict[str, Any]] = None,
        threshold: float = 0.0,
        mode: str = "default",
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

        query = str(record.get("query") or "").strip()
        if not query:
            raw_text = (
                record.get("consulting_content")
                or record.get("raw_text")
                or record.get("text")
                or ""
            )
            query = cls._extract_query_from_raw_text(str(raw_text))
        if not query:
            query = "(빈 질의)"

        query, derived_trace = cls._derive_query_and_trace(
            record=record,
            query=query,
            routing_trace=base_trace,
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
            details = {
                "derived_query": derived_trace.get("derived_query"),
                "search_query": derived_trace.get("search_query"),
                "keyword_terms": derived_trace.get("keyword_terms"),
                "collection_name": derived_trace.get("collection_name"),
                "effective_top_k": derived_trace.get("effective_top_k"),
                "filters": derived_trace.get("filters"),
                "threshold": derived_trace.get("threshold"),
                "topic_type": derived_trace.get("topic_type"),
                "complexity_level": derived_trace.get("complexity_level"),
                "request_segments": derived_trace.get("request_segments"),
                "route_key": derived_trace.get("route_key"),
                "strategy_id": derived_trace.get("strategy_id"),
                "retrieval_policy": derived_trace.get("retrieval_policy"),
                "prompt_mode": derived_trace.get("prompt_mode"),
                "context_count": 0,
            }
            raise NoEvidenceError(
                "검색 근거가 0개라 프롬프트를 구성할 수 없습니다. CHROMA_DB_PATH/collection_name을 확인하거나 top_k/threshold/filters를 조정하세요.",
                details=details,
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
                analysis = build_analyzer_output(query, topic_type=topic_type or "general")
                derived_trace.setdefault("complexity_level", str(analysis.get("complexity_level") or "medium"))
                derived_trace.setdefault("complexity_score", float(analysis.get("complexity_score") or 0.5))
                request_segments = analysis.get("request_segments")
                if isinstance(request_segments, list) and request_segments:
                    derived_trace.setdefault("request_segments", request_segments[:5])
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
            raise NoEvidenceError(
                "근거 컨텍스트가 0개입니다. 근거 없이 답변을 생성하지 않도록 실패 처리합니다.",
                details={
                    "derived_query": routing_trace.get("derived_query"),
                    "topic_type": topic_type,
                    "complexity_level": complexity_level,
                    "request_segments": request_segments,
                    "retrieval_policy": retrieval_policy,
                    "prompt_mode": routing_trace.get("prompt_mode"),
                    "context_count": 0,
                },
            )

        if not isinstance(request_segments, list):
            request_segments = []
        request_segments = [str(item).strip() for item in request_segments if str(item).strip()]

        topic_guide = cls.TOPIC_GUIDANCE.get(topic_type, cls.TOPIC_GUIDANCE["general"])
        complexity_guide = cls.COMPLEXITY_GUIDANCE.get(complexity_level, cls.COMPLEXITY_GUIDANCE["medium"])
        policy_guide = cls.POLICY_GUIDANCE.get(retrieval_policy, cls.POLICY_GUIDANCE["general"])
        prompt_mode = str(routing_trace.get("prompt_mode") or "default").lower()
        is_compact = prompt_mode == "compact"
        is_force_json = prompt_mode == "force_json"
        record_guide = cls._build_record_guide(record or {}) if record else ""

        segment_guide = ""
        if request_segments:
            numbered = "\n".join(f"- 섹션 {idx + 1}: {segment}" for idx, segment in enumerate(request_segments))
            segment_guide = (
                "\n세그먼트별로 답변을 나누고 각 세그먼트마다 action_items 1개 이상을 붙이세요:\n"
                f"{numbered}"
            )

        snippet_max_chars = 120 if is_compact else 200
        citation_snippet_max_chars = 120 if is_compact else 200
        context_limit = 2 if is_compact else len(context)
        citations_max = 2 if is_compact else 3

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

        base_rules = (
            "설명/주석/마크다운/코드블록(``` 포함)은 절대 출력하지 마세요.\n"
            "출력은 반드시 '{' 로 시작하고 '}' 로 끝나야 합니다.\n"
            "JSON 객체 외의 다른 텍스트를 절대 출력하지 마세요.\n"
            "JSON 유효성: 키/문자열은 큰따옴표(\")만 사용, trailing comma(끝 콤마) 금지, NaN/Infinity 금지.\n"
            "추가 키 금지: JSON Schema의 additionalProperties=false를 반드시 지키세요(스키마에 없는 키 출력 금지).\n"
            "필수 키 누락 금지: answer, citations, limitations, structured_output.\n"
            "limitations는 빈 문자열 금지(필요 시 1개 이상 작성).\n"
            "structured_output.summary는 빈 문자열 금지, action_items는 2개 이상 필수, request_segments는 배열로 유지하세요.\n"
            "citations는 아래 검색 컨텍스트에서만 선택하고 chunk_id/case_id를 그대로 복사하세요.\n"
            f"citations는 1~{citations_max}개만 출력하세요.\n"
            "각 citation은 chunk_id/case_id/snippet/relevance_score를 반드시 포함하세요.\n"
            f"citation.snippet은 아래 컨텍스트의 snippet에서 그대로 발췌(부분 문자열 허용)하고 빈 문자열 금지, {citation_snippet_max_chars}자 이하로 유지하세요.\n"
            "citation.relevance_score는 컨텍스트의 score 값을 그대로 사용(0~1).\n"
            "answer에는 citations 개수 N에 대해 [[출처 1]]..[[출처 N]] 토큰을 각각 정확히 1회 포함하고, 그 외 [[출처 ...]] 토큰은 금지합니다.\n"
        )

        if is_force_json:
            mode_rules = (
                "[force_json 모드] JSON만 강제합니다.\n"
                "아래 JSON Schema의 required/형식을 절대 위반하지 마세요.\n"
            )
        elif is_compact:
            mode_rules = (
                "[compact 모드] 컨텍스트가 짧으니 과장/추측 금지.\n"
                "answer 형식: 공문형 민원회신(1~4항)으로 간결하게 작성하세요(너무 길게 늘어지지 않게).\n"
                "형식 가이드: 1. 인사/감사  2. 민원 요지  3. 검토 결과(가/나/다)  4. 추가 안내(담당 부서 문의).\n"
                "구체 수치/날짜/조례/노선개편 등 사실은 컨텍스트에 있는 내용만 사용하고, 없으면 '검토/협의/모니터링' 등으로 표현하세요.\n"
                "답변 톤: 행정기관 회신 문체(존댓말)로 작성하세요.\n"
                "조치(action_items)는 우선순위를 반영해 2개 이상 작성(예: '1순위: ...', '2순위: ...').\n"
                "compact에서는 제공되는 컨텍스트가 최대 2개이며 snippet이 짧습니다.\n"
            )
        else:
            mode_rules = (
                "answer 형식: 공문형 민원회신으로 작성하세요.\n"
                "반드시 아래 구조를 따르세요(문장/문단 구분은 \"\\n\" 사용 권장):\n"
                "1. 우리 시 시정 발전에 관심을 두셔서 감사드립니다... (인사/감사)\n"
                "2. 귀하의 민원 내용은 \"...\"에 관한 것으로 이해됩니다. (민원 요지 1문단)\n"
                "3. 귀하의 질의 사항에 대한 검토 의견은 다음과 같습니다.\n"
                "   가. (컨텍스트 근거 기반 사실/현황/조치)\n"
                "   나. (한계/제약/절차 안내: 예산, 관계기관 협의, 현장 확인 등)\n"
                "   다. (향후 계획/점검/개선 약속: 모니터링, 협의, 안내 등)\n"
                "4. 추가 설명이 필요하시면 성남시 해당 업무 담당부서로 문의해 주시기 바랍니다. 감사합니다.\n"
                "금지: '근거:'라는 라벨로 요약하는 답변, 1문장 요약만 제시하는 답변.\n"
                "사실성 규칙: 구체 수치/날짜/조례/노선개편 등은 컨텍스트에 있는 내용만 단정적으로 쓰고, 없으면 '검토/확인/협의 예정'으로 표현하세요.\n"
                "조치(action_items)는 우선순위를 반영해 2개 이상 작성(예: '1순위: ...', '2순위: ...').\n"
                "세그먼트가 있으면 각 세그먼트마다 action_items 1개 이상을 직접 대응시키세요.\n"
            )

        instruction_block = base_rules + mode_rules

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
            "출력 예시(JSON):\n"
            "{"
            "\"answer\":\"1. 우리 시 시정 발전에 관심을 두셔서 감사드립니다.\\n\\n2. 귀하의 민원 내용은 \\\"...\\\"에 관한 것으로 이해됩니다.\\n\\n3. 검토 의견은 다음과 같습니다.\\n가. ...\\n나. ...\\n다. ...\\n\\n4. 추가 설명이 필요하시면 담당부서로 문의해 주시기 바랍니다. 감사합니다. [[출처 1]]\","
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
            + f"\n운영 정책 지시문: {policy_guide}"
            + record_guide
            + f"{segment_guide}\n\n"
            + f"질문: {query}\n\n"
            + "검색 컨텍스트:\n"
            + "\n".join(context_lines)
        )

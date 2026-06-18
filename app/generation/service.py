"""
생성 서비스 (Generation)

Week 1 기준선 구현:
- Ollama 호출
- JSON 파싱/재시도
- citation 포함 QA 응답 생성
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx

from app.core.logging import pipeline_logger
from app.core.exceptions import GenerationError, RetrievalError
from app.core.config import settings
from app.generation.prompts.prompt_factory import PromptFactory
from app.generation.parsing.json_utils import (
    build_qa_response_schema,
    extract_json_string,
    normalize_confidence,
    parse_qa_json_response,
)


class GenerationService:
    """생성 서비스"""

    def __init__(self):
        """초기화"""
        self.logger = pipeline_logger
        self.ollama_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    def _extract_json_string(self, text: str) -> str:
        """응답 텍스트에서 JSON 블록을 추출한다."""
        return extract_json_string(text)

    def _normalize_confidence(self, value: Any) -> float:
        """confidence를 0~1 number로 정규화한다."""
        return normalize_confidence(value)

    async def call_ollama(
        self,
        prompt: str,
        temperature: float = 0.7,
        response_schema: Dict[str, Any] | None = None,
    ) -> str:
        """
        Ollama LLM 호출

        Args:
            prompt: 프롬프트
            temperature: 온도 파라미터 (0~1)

        Returns:
            생성된 텍스트
            
        Raises:
            GenerationError: 다음 경우 발생
                - MODEL_NOT_READY (503): Ollama 미기동/연결거부
                - MODEL_NOT_FOUND (404): 모델 미존재
                - MODEL_TIMEOUT (504): 응답 시간 초과
                - PROCESSING_ERROR (500): 기타 HTTP 오류
        """
        from app.core.logging import log_ollama_call, log_ollama_error
        
        endpoint = "/api/generate"
        stage = "init"
        
        try:
            # 호출 시작 로깅
            log_ollama_call(
                self.logger,
                endpoint=endpoint,
                model=self.model,
                ollama_base_url=self.ollama_url,
                timeout=self.timeout,
                temperature=temperature,
            )
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": response_schema or "json",
                "options": {
                    "temperature": temperature,
                    "num_predict": settings.GENERATION_NUM_PREDICT,
                    "num_ctx": settings.GENERATION_NUM_CTX,
                },
            }

            url = f"{self.ollama_url.rstrip('/')}{endpoint}"
            
            stage = "connect"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                stage = "request"
                response = await client.post(url, json=payload)
                
                # HTTP 상태코드 확인
                if response.status_code != 200:
                    stage = "response_check"
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                
                stage = "parse"
                data = response.json()
                text = str(data.get("response", "")).strip()
                
            if not text:
                raise GenerationError(
                    "Ollama 응답이 비어 있습니다.",
                    code="PROCESSING_ERROR",
                    retryable=True,
                    details={"stage": stage},
                    upstream_status=200,
                )

            return text
            
        # 1. 연결 거부/Ollama 미기동
        except httpx.ConnectError as e:
            log_ollama_error(
                self.logger,
                endpoint=endpoint,
                model=self.model,
                ollama_base_url=self.ollama_url,
                timeout=self.timeout,
                stage=stage,
                upstream_status=None,
                error_code="MODEL_NOT_READY",
                error_message=f"Ollama 연결 거부: {str(e)}",
                retryable=True,
            )
            raise GenerationError(
                "Ollama 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.",
                code="MODEL_NOT_READY",
                retryable=True,
                details={
                    "stage": stage,
                    "error_type": "ConnectError",
                },
                upstream_status=None,
            ) from e
        
        # 2. 연결 타임아웃
        except httpx.ConnectTimeout as e:
            log_ollama_error(
                self.logger,
                endpoint=endpoint,
                model=self.model,
                ollama_base_url=self.ollama_url,
                timeout=self.timeout,
                stage=stage,
                upstream_status=None,
                error_code="MODEL_NOT_READY",
                error_message=f"Ollama 연결 타임아웃: {str(e)}",
                retryable=True,
            )
            raise GenerationError(
                "Ollama 서버 연결이 시간 초과되었습니다. 잠시 후 다시 시도해주세요.",
                code="MODEL_NOT_READY",
                retryable=True,
                details={
                    "stage": stage,
                    "error_type": "ConnectTimeout",
                    "timeout": self.timeout,
                },
                upstream_status=None,
            ) from e
        
        # 3. 읽기 타임아웃 (응답 시간 초과)
        except httpx.ReadTimeout as e:
            log_ollama_error(
                self.logger,
                endpoint=endpoint,
                model=self.model,
                ollama_base_url=self.ollama_url,
                timeout=self.timeout,
                stage=stage,
                upstream_status=None,
                error_code="MODEL_TIMEOUT",
                error_message=f"Ollama 읽기 타임아웃: {str(e)}",
                retryable=True,
            )
            raise GenerationError(
                "응답 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
                code="MODEL_TIMEOUT",
                retryable=True,
                details={
                    "stage": stage,
                    "error_type": "ReadTimeout",
                    "timeout": self.timeout,
                },
                upstream_status=None,
            ) from e
        
        # 4. HTTP 상태 오류 (4xx, 5xx)
        except httpx.HTTPStatusError as e:
            upstream_status = e.response.status_code
            
            # 4-1. 404: 모델 미존재
            if upstream_status == 404:
                log_ollama_error(
                    self.logger,
                    endpoint=endpoint,
                    model=self.model,
                    ollama_base_url=self.ollama_url,
                    timeout=self.timeout,
                    stage=stage,
                    upstream_status=upstream_status,
                    error_code="MODEL_NOT_FOUND",
                    error_message=f"모델을 찾을 수 없음: {self.model}",
                    retryable=False,
                )
                raise GenerationError(
                    f"요청하신 모델 '{self.model}'을 찾을 수 없습니다. "
                    "Ollama에 해당 모델이 설치되어 있는지 확인해주세요.",
                    code="MODEL_NOT_FOUND",
                    retryable=False,
                    details={
                        "stage": stage,
                        "error_type": "HTTPStatusError",
                        "model": self.model,
                    },
                    upstream_status=upstream_status,
                ) from e
            
            # 4-2. 503: 서비스 불가 (메모리/기타 리소스 부족)
            elif upstream_status == 503:
                log_ollama_error(
                    self.logger,
                    endpoint=endpoint,
                    model=self.model,
                    ollama_base_url=self.ollama_url,
                    timeout=self.timeout,
                    stage=stage,
                    upstream_status=upstream_status,
                    error_code="MODEL_NOT_READY",
                    error_message="Ollama 서비스 임시 불가",
                    retryable=True,
                )
                raise GenerationError(
                    "Ollama 서버가 현재 요청을 처리할 수 없습니다. "
                    "메모리 부족이거나 서버가 준비 중일 수 있습니다.",
                    code="MODEL_NOT_READY",
                    retryable=True,
                    details={
                        "stage": stage,
                        "error_type": "HTTPStatusError",
                    },
                    upstream_status=upstream_status,
                ) from e
            
            # 4-3. 기타 5xx: 일반 처리 오류
            elif 500 <= upstream_status < 600:
                log_ollama_error(
                    self.logger,
                    endpoint=endpoint,
                    model=self.model,
                    ollama_base_url=self.ollama_url,
                    timeout=self.timeout,
                    stage=stage,
                    upstream_status=upstream_status,
                    error_code="PROCESSING_ERROR",
                    error_message=f"Ollama 서버 오류: HTTP {upstream_status}",
                    retryable=True,
                )
                raise GenerationError(
                    f"Ollama 서버에서 오류가 발생했습니다 (HTTP {upstream_status}). "
                    f"잠시 후 다시 시도해주세요.",
                    code="PROCESSING_ERROR",
                    retryable=True,
                    details={
                        "stage": stage,
                        "error_type": "HTTPStatusError",
                    },
                    upstream_status=upstream_status,
                ) from e
            
            # 4-4. 기타 4xx: 클라이언트 오류 (재시도 불가)
            else:
                log_ollama_error(
                    self.logger,
                    endpoint=endpoint,
                    model=self.model,
                    ollama_base_url=self.ollama_url,
                    timeout=self.timeout,
                    stage=stage,
                    upstream_status=upstream_status,
                    error_code="BAD_REQUEST",
                    error_message=f"Ollama 클라이언트 오류: HTTP {upstream_status}",
                    retryable=False,
                )
                raise GenerationError(
                    f"Ollama 요청이 올바르지 않습니다 (HTTP {upstream_status}).",
                    code="BAD_REQUEST",
                    retryable=False,
                    details={
                        "stage": stage,
                        "error_type": "HTTPStatusError",
                    },
                    upstream_status=upstream_status,
                ) from e
        
        # 5. 기타 httpx 오류
        except httpx.HTTPError as e:
            log_ollama_error(
                self.logger,
                endpoint=endpoint,
                model=self.model,
                ollama_base_url=self.ollama_url,
                timeout=self.timeout,
                stage=stage,
                upstream_status=None,
                error_code="PROCESSING_ERROR",
                error_message=f"Ollama HTTP 오류: {type(e).__name__} - {str(e)}",
                retryable=True,
            )
            raise GenerationError(
                f"Ollama 호출 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=True,
                details={
                    "stage": stage,
                    "error_type": type(e).__name__,
                },
                upstream_status=None,
            ) from e
        
        # 6. 기타 모든 예외
        except GenerationError:
            # GenerationError는 그대로 전파
            raise
        except Exception as e:
            log_ollama_error(
                self.logger,
                endpoint=endpoint,
                model=self.model,
                ollama_base_url=self.ollama_url,
                timeout=self.timeout,
                stage=stage,
                upstream_status=None,
                error_code="PROCESSING_ERROR",
                error_message=f"Ollama 예기치 않은 오류: {type(e).__name__} - {str(e)}",
                retryable=True,
            )
            raise GenerationError(
                f"Ollama 호출 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=True,
                details={
                    "stage": stage,
                    "error_type": type(e).__name__,
                },
                upstream_status=None,
            ) from e

    async def build_rag_prompt(
        self,
        query: str,
        context: List[Dict[str, Any]],
        routing_trace: Dict[str, Any] | None = None,
        mode: str = "default",
    ) -> str:
        """
        RAG 프롬프트 구성

        Args:
            query: 사용자 질문
            context: 검색 결과 컨텍스트

        Returns:
            완성된 프롬프트
        """
        try:
            self.logger.info(f"RAG 프롬프트 구성: {len(context)}개 컨텍스트")
            base_trace = dict(routing_trace or {})
            if mode == "force_json":
                base_trace["prompt_mode"] = "force_json"
            elif mode == "compact":
                base_trace["prompt_mode"] = "compact"

            return PromptFactory.build(query=query, context=context, routing_trace=base_trace)
        except RetrievalError:
            raise
        except Exception as e:
            self.logger.error(f"프롬프트 구성 실패: {str(e)}")
            raise GenerationError(
                f"프롬프트 구성 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=False,
                details={"stage": "prompt"},
            ) from e

    async def build_rag_prompt_from_record(
        self,
        record: Dict[str, Any],
        context: List[Dict[str, Any]],
        routing_trace: Dict[str, Any] | None = None,
        mode: str = "default",
    ) -> str:
        """성남시_test_10 같은 원문 레코드 기반으로 RAG 프롬프트를 구성한다."""
        try:
            self.logger.info(f"원문 레코드 기반 RAG 프롬프트 구성: {len(context)}개 컨텍스트")
            base_trace = dict(routing_trace or {})
            if mode == "force_json":
                base_trace["prompt_mode"] = "force_json"
            elif mode == "compact":
                base_trace["prompt_mode"] = "compact"

            return PromptFactory.build_from_dataset_record(record=record, context=context, routing_trace=base_trace)
        except RetrievalError:
            raise
        except Exception as e:
            self.logger.error(f"원문 레코드 기반 프롬프트 구성 실패: {str(e)}")
            raise GenerationError(
                f"프롬프트 구성 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=False,
                details={"stage": "prompt"},
            ) from e

    async def build_rag_prompt_from_record_autoretrieve(
        self,
        record: Dict[str, Any],
        routing_trace: Dict[str, Any] | None = None,
        mode: str = "default",
        top_k: int | None = None,
        collection_name: str = settings.DEFAULT_CHROMA_COLLECTION,
        filters: Dict[str, Any] | None = None,
        threshold: float = 0.0,
    ) -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """원문 레코드만 입력받아 (검색 포함) RAG 프롬프트를 구성한다.

        Returns:
            (prompt, context, derived_trace)
        """
        try:
            prompt, context, derived_trace = await PromptFactory.build_from_dataset_record_autoretrieve(
                record=record,
                routing_trace=routing_trace,
                top_k=top_k,
                collection_name=collection_name,
                filters=filters,
                threshold=threshold,
                mode=mode,
            )
            derived_query = str(derived_trace.get("derived_query") or "")
            search_query = str(derived_trace.get("search_query") or "")
            self.logger.info(
                "autoretrieve trace: derived_query=%s, search_query=%s, collection=%s, top_k=%s, filters=%s, threshold=%s, topic=%s, complexity=%s, route=%s, strategy=%s, policy=%s",
                derived_query,
                search_query,
                str(derived_trace.get("collection_name") or collection_name),
                str(derived_trace.get("effective_top_k") or top_k),
                str(derived_trace.get("filters") or filters or {}),
                str(derived_trace.get("threshold") or threshold),
                str(derived_trace.get("topic_type") or ""),
                str(derived_trace.get("complexity_level") or ""),
                str(derived_trace.get("route_key") or ""),
                str(derived_trace.get("strategy_id") or ""),
                str(derived_trace.get("retrieval_policy") or ""),
            )
            self.logger.info(f"원문 레코드 자동검색 RAG 프롬프트 구성 완료: {len(context)}개 컨텍스트")
            return prompt, context, derived_trace
        except RetrievalError as e:
            self.logger.warning(
                "원문 레코드 자동검색 프롬프트 구성 실패(retrieval): %s details=%s",
                str(e),
                str(getattr(e, "details", {})),
            )
            raise
        except Exception as e:
            self.logger.error(f"원문 레코드 자동검색 프롬프트 구성 실패: {str(e)}")
            raise GenerationError(
                f"프롬프트 구성 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=False,
                details={"stage": "prompt", "mode": mode},
            ) from e

    async def parse_json_response(self, text: str) -> Dict[str, Any]:
        """
        JSON 응답 파싱

        Args:
            text: LLM이 생성한 텍스트

        Returns:
            파싱된 JSON 객체
        """
        self.logger.debug("JSON 응답 파싱")
        return parse_qa_json_response(text)

    async def parse_json_response_relaxed(
        self,
        text: str,
        context: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """strict 파싱 실패 시 Week6/모델 변형 응답을 완화 파싱한다."""
        try:
            json_str = self._extract_json_string(text)
            payload = json.loads(json_str)
        except GenerationError:
            raise
        except Exception as e:
            raise GenerationError(
                "모델 응답을 JSON으로 파싱하지 못했습니다.",
                code="PARSE_JSON_DECODE_ERROR",
                retryable=True,
                details={"stage": "decode", "reason": str(e)},
            ) from e

        if not isinstance(payload, dict):
            raise GenerationError(
                "모델 응답 JSON이 객체 형식이 아닙니다.",
                code="PARSE_SCHEMA_MISMATCH",
                retryable=True,
                details={"stage": "schema", "reason": "root_not_object"},
            )

        answer = str(payload.get("answer") or "").strip()
        if not answer:
            for key in ("response", "content", "output", "result", "final_answer"):
                value = str(payload.get(key) or "").strip()
                if value:
                    answer = value
                    break
        if not answer:
            raise GenerationError(
                "answer 및 대체 응답 필드가 모두 비어 있습니다.",
                code="PARSE_SCHEMA_MISMATCH",
                retryable=True,
                details={"stage": "schema", "field": "answer"},
            )

        raw_citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
        citations: List[Dict[str, Any]] = []
        for item in raw_citations:
            if not isinstance(item, dict):
                continue

            snippet = str(item.get("snippet") or item.get("quote") or "").strip()
            citation: Dict[str, Any] = {
                "chunk_id": str(item.get("chunk_id") or ""),
                "case_id": str(item.get("case_id") or item.get("doc_id") or ""),
                "snippet": snippet,
                "relevance_score": normalize_confidence(item.get("relevance_score", 0.5)),
            }
            doc_id = str(item.get("doc_id") or "").strip()
            if doc_id:
                citation["doc_id"] = doc_id
            citations.append(citation)

        limitations_raw = payload.get("limitations")
        if isinstance(limitations_raw, list):
            limitations = "; ".join(
                [str(item).strip() for item in limitations_raw if str(item).strip()]
            )
        else:
            limitations = str(limitations_raw or "").strip()

        if not limitations:
            limitations = "검색 범위 및 데이터 품질에 따라 답변이 제한될 수 있습니다."

        return {
            "answer": answer,
            "citations": citations,
            "confidence": normalize_confidence(payload.get("confidence", 0.5)),
            "limitations": limitations,
            "structured_output": payload.get("structured_output")
            if isinstance(payload.get("structured_output"), dict)
            else {},
        }

    def _build_fast_fallback_from_context(
        self,
        context: List[Dict[str, Any]],
        legal_articles: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """모델 재호출 없이 즉시 사용할 수 있는 최소 응답을 구성한다."""
        if context:
            first = context[0]
            snippet = str(first.get("snippet", "")).strip()
            answer = (
                "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
                "2. 귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다. "
                "접수된 취지와 검색된 유사 사례를 참고하되, 해당 민원의 사실관계와 처리 권한은 별도로 확인해야 합니다.\n\n"
                "3. 검토 의견은 다음과 같습니다. 현재 모델 응답이 정해진 출력 형식을 충족하지 않아 구체적인 처리 결과를 확정하여 안내하기 어렵습니다. "
                "담당부서에서 현장 여건, 소관 권한, 관련 기준을 확인한 뒤 조치 가능 여부와 후속 절차를 안내드리겠습니다.\n\n"
                "4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝."
            ).strip()
            citations = [
                {
                    "chunk_id": str(first.get("chunk_id", "")),
                    "case_id": str(first.get("case_id", "")),
                    "snippet": snippet[:240],
                    "relevance_score": normalize_confidence(first.get("score", 0.5)),
                }
            ]
        else:
            answer = (
                "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
                "2. 현재 확인 가능한 자료가 충분하지 않아 민원 취지, 발생 장소, 관련 법령 또는 처리 기준에 대한 담당부서 확인이 필요합니다.\n\n"
                "3. 접수 내용과 추가 자료가 확인되면 현장 여건과 행정 처리 가능 범위를 검토한 뒤 필요한 조치 가능 여부를 안내드리겠습니다. "
                "다만 구체적인 처분이나 일정은 소관 부서의 사실관계 확인 결과에 따라 달라질 수 있습니다.\n\n"
                "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 절차와 보완 필요 사항을 친절히 안내해 드리겠습니다. 감사합니다. 끝."
            )
            citations = []

        return {
            "answer": answer,
            "citations": citations,
            "confidence": 0.35,
            "limitations": "모델 응답 파싱 실패로 컨텍스트 기반 폴백을 사용했습니다.",
            "structured_output": {
                "summary": "모델 출력 형식 오류로 담당부서의 사실관계 확인이 필요한 민원",
                "action_items": [
                    "민원 사실관계와 현장 여건 확인",
                    "소관 권한과 적용 기준 확인 후 처리 결과 안내",
                ],
                "request_segments": [],
            },
        }

    async def build_citations(
        self, response: str, context: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Citation 생성

        Args:
            response: 생성된 응답
            context: 검색 결과

        Returns:
            Citation 리스트
        """
        try:
            self.logger.info(f"Citation 생성: {len(context)}개 소스")

            citations: List[Dict[str, Any]] = []
            for item in context[:3]:
                citation: Dict[str, Any] = {
                    "chunk_id": str(item.get("chunk_id", "")),
                    "case_id": str(item.get("case_id", "")),
                    "snippet": str(item.get("snippet", "")),
                    "relevance_score": self._normalize_confidence(
                        item.get("score", item.get("relevance_score", 0.5))
                    ),
                }
                doc_id = str(item.get("doc_id", "")).strip()
                if doc_id:
                    citation["doc_id"] = doc_id

                citations.append(citation)

            return citations
        except Exception as e:
            self.logger.error(f"Citation 생성 실패: {str(e)}")
            raise GenerationError(
                f"Citation 생성 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=True,
            ) from e

    @staticmethod
    def _normalize_generation_signals(
        query_signals: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        signals = dict(query_signals or {})
        for key in (
            "legal_ref_ids",
            "legal_ref_names",
            "key_terms",
            "responsible_units",
        ):
            value = signals.get(key)
            signals[key] = value if isinstance(value, list) else []
        urgency = signals.get("urgency_level")
        if isinstance(urgency, dict):
            urgency = urgency.get("level")
        signals["urgency_level"] = str(urgency or "").strip()
        signals["responsible_units_source"] = str(signals.get("responsible_units_source") or "").strip()
        return signals

    def _prepare_legal_context(
        self,
        query: str,
        query_signals: Dict[str, Any] | None = None,
    ):
        """질의 → 법령 후보 → 조문 검색 결과와 관측 상태를 반환한다."""
        try:
            from app.core.config import settings as _st
            if not getattr(_st, "ENABLE_LEGAL_CITATIONS", True):
                return [], "", {"status": "disabled", "error": ""}
            from app.structuring.legal_dictionary import get_legal_ref_matcher
            from app.structuring.enrichment import (
                build_key_terms, normalize_entity_texts,
            )
            from app.generation.citation.legal_citation import (
                retrieve_legal_context, build_legal_context_block, LEGAL_CITATION_INSTRUCTION,
            )
            signals = self._normalize_generation_signals(query_signals)
            ref_ids = [
                str(item).strip()
                for item in signals["legal_ref_ids"]
                if str(item).strip()
            ]
            ref_names = [
                str(item).strip()
                for item in signals["legal_ref_names"]
                if str(item).strip()
            ]
            if ref_ids:
                names_are_aligned = len(ref_names) == len(ref_ids)
                refs = [
                    {
                        "law_id": law_id,
                        "name": ref_names[index] if names_are_aligned else "",
                        "source": "be1_query_signals",
                    }
                    for index, law_id in enumerate(ref_ids)
                ]
            else:
                refs = get_legal_ref_matcher().match(query)

            kt = [
                str(item).strip()
                for item in signals["key_terms"]
                if str(item).strip()
            ]
            if not kt:
                et = normalize_entity_texts([], query)
                kt = build_key_terms(query, et, refs)
            articles = retrieve_legal_context(query, refs, key_terms=kt, top_k=5)
            if not articles:
                return [], "", {"status": "no_candidates", "error": ""}
            extra = "\n\n" + LEGAL_CITATION_INSTRUCTION + "\n" + build_legal_context_block(articles)
            return articles, extra, {"status": "grounded", "error": ""}
        except Exception as e:  # noqa: BLE001
            self.logger.warning("법령 그라운딩 준비 생략: %s", e)
            return [], "", {
                "status": "error",
                "error": f"{type(e).__name__}: legal grounding unavailable",
            }

    @staticmethod
    def _build_legal_retry_context(
        articles: List[Dict[str, Any]],
        mode: str,
    ) -> str:
        """Reduce legal context on recovery attempts without dropping evidence."""
        if not articles:
            return ""

        from app.generation.citation.legal_citation import (
            LEGAL_CITATION_INSTRUCTION,
            build_legal_context_block,
        )

        limits = {
            "default": (5, 280),
            "force_json": (3, 180),
            "compact": (1, 120),
        }
        max_articles, max_chars = limits.get(mode, limits["default"])
        return (
            "\n\n"
            + LEGAL_CITATION_INSTRUCTION
            + "\n"
            + build_legal_context_block(
                articles,
                max_articles=max_articles,
                max_chars=max_chars,
            )
        )

    @staticmethod
    def _append_output_contract(prompt: str) -> str:
        """Keep the JSON-only instruction last after supplemental context."""
        return (
            prompt
            + "\n\n[FINAL OUTPUT CONTRACT]\n"
            + "Return exactly one JSON object and no prose, markdown, or code fence. "
            + "The object must contain non-empty answer, citations, limitations, "
            + "and structured_output fields."
        )

    def _build_urgency_context(
        self,
        query_signals: Dict[str, Any] | None = None,
    ) -> str:
        """BE1 긴급도 신호를 과단정 없이 답변 안전 안내에 반영한다."""
        signals = self._normalize_generation_signals(query_signals)
        level = signals["urgency_level"]
        if level not in {"긴급", "높음"}:
            return ""

        units = [
            str(item).strip()
            for item in signals["responsible_units"]
            if str(item).strip()
        ]
        unit_hint = f" 담당부서 후보는 {', '.join(units[:2])}입니다." if units else ""
        return (
            "\n\n[긴급도 보조 신호]\n"
            f"- BE1 긴급도 후보: {level}.{unit_hint}\n"
            "- 이 값은 미보정 보조 신호이므로 긴급성을 확정하거나 점수를 노출하지 마세요.\n"
            "- 민원 원문에 생명·신체·화재·가스·붕괴 등 즉시 위험 근거가 있을 때만 "
            "현장 접근 중단과 112/119 등 긴급 신고를 답변 서두에 안내하세요.\n"
            "- 즉시 위험 근거가 부족하면 담당부서의 신속한 현장 확인과 연락 방법을 우선 안내하고, "
            "확인되지 않은 부서명·전화번호·처리기한은 만들지 마세요."
        )

    def _apply_legal_grounding(
        self,
        result: Dict[str, Any],
        articles,
        grounding_status: Dict[str, str],
    ) -> Dict[str, Any]:
        """답변의 법령 인용을 검색 조문과 대조 → 환각 제거 + legal_citations 부착."""
        try:
            result.setdefault("legal_citations", [])
            result.setdefault("legal_citation_warnings", [])
            if grounding_status.get("status") in {"disabled", "not_requested"}:
                return result
            from app.generation.citation.legal_citation import ground_legal_citations
            g = ground_legal_citations(result.get("answer", ""), articles or [])
            result["answer"] = g["answer"]
            result["legal_citations"] = g["valid"]
            result["legal_citation_warnings"] = g["warnings"]
        except Exception as e:  # noqa: BLE001
            self.logger.warning("법령 인용 검증 생략: %s", e)
            grounding_status["status"] = "error"
            grounding_status["error"] = (
                f"{type(e).__name__}: legal citation validation unavailable"
            )
        return result

    async def generate_qa(
        self,
        query: str,
        context: List[Dict[str, Any]],
        routing_trace: Dict[str, Any] | None = None,
        query_signals: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        QA 응답 생성 (RAG)

        Args:
            query: 사용자 질문
            context: 검색 결과

        Returns:
            {
                "question": "...",
                "answer": "...",
                "confidence": 0.85,
                "citations": [...],
                "model": "exaone3.5:7.8b"
            }
        """
        try:
            self.logger.info(f"QA 응답 생성: query='{query}'")

            parsed: Dict[str, Any] = {}
            last_parse_error: GenerationError | None = None
            generation_mode = "default"
            fallback_used = False
            retry_steps = [
                {"stage": "default", "mode": "default", "temperature": 0.2},
                {"stage": "compact", "mode": "compact", "temperature": 0.0},
            ]
            retry_logs: List[Dict[str, Any]] = []
            legal_articles, _legal_extra, legal_grounding = self._prepare_legal_context(
                query,
                query_signals=query_signals,
            )
            urgency_extra = self._build_urgency_context(query_signals)

            for attempt_index, step in enumerate(retry_steps, start=1):
                try:
                    prompt = await self.build_rag_prompt(
                        query,
                        context,
                        routing_trace=routing_trace,
                        mode=str(step["mode"]),
                    )
                    legal_retry_context = self._build_legal_retry_context(
                        legal_articles,
                        str(step["mode"]),
                    )
                    if legal_retry_context:
                        prompt = prompt + legal_retry_context
                    if urgency_extra:
                        prompt = prompt + urgency_extra
                    prompt = self._append_output_contract(prompt)
                    response_text = await self.call_ollama(
                        prompt,
                        temperature=float(step["temperature"]),
                        response_schema=build_qa_response_schema(
                            context,
                            citations_max=1,
                        ),
                    )
                    parsed = await self.parse_json_response(response_text)
                    generation_mode = str(step["mode"])
                    break
                except GenerationError as e:
                    if not str(getattr(e, "code", "")).startswith("PARSE_"):
                        raise

                    retry_logs.append(
                        {
                            "attempt": attempt_index,
                            "stage": step["stage"],
                            "code": e.code,
                            "message": str(e),
                        }
                    )
                    self.logger.warning(
                        f"QA JSON 파싱 재시도 {attempt_index}/{len(retry_steps)}: {str(e)}"
                    )

            if not parsed:
                self.logger.warning("QA JSON 파싱 재시도 소진: fast fallback 사용")
                parsed = self._build_fast_fallback_from_context(
                    context,
                    legal_articles=legal_articles,
                )
                generation_mode = "fast_fallback"
                fallback_used = True

            citations = parsed.get("citations") or await self.build_citations("", context)

            result = {
                "question": query,
                "answer": str(parsed.get("answer", "")).strip(),
                "confidence": self._normalize_confidence(parsed.get("confidence")),
                "citations": citations,
                "limitations": str(
                    parsed.get("limitations")
                    or "검색 범위 및 데이터 품질에 따라 답변이 제한될 수 있습니다."
                ),
                "structured_output": parsed.get("structured_output")
                if isinstance(parsed.get("structured_output"), dict)
                else {},
                "model": self.model,
                "generation_metadata": {
                    "fallback_used": fallback_used,
                    "parse_retry_count": len(retry_logs),
                    "grounding_evidence_count": len(context),
                    "citation_count": len(citations),
                    "generation_mode": generation_mode,
                    "legal_grounding_status": legal_grounding["status"],
                    "legal_grounding_error": legal_grounding["error"],
                },
            }

            result = self._apply_legal_grounding(
                result,
                legal_articles,
                legal_grounding,
            )
            result["generation_metadata"].update(
                {
                    "legal_grounding_status": legal_grounding["status"],
                    "legal_grounding_error": legal_grounding["error"],
                }
            )
            self.logger.info("QA 응답 생성 완료")
            return result

        except GenerationError:
            raise
        except Exception as e:
            self.logger.error(f"QA 응답 생성 실패: {str(e)}")
            raise GenerationError(
                f"QA 응답 생성 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=True,
            ) from e


# 싱글톤
_generation_service = None


def get_generation_service() -> GenerationService:
    """생성 서비스 인스턴스 반환"""
    global _generation_service
    if _generation_service is None:
        _generation_service = GenerationService()
    return _generation_service

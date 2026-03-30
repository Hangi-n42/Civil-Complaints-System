"""
생성 서비스 (Generation)

Week 1 기준선 구현:
- Ollama 호출
- JSON 파싱/재시도
- citation 포함 QA 응답 생성
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from app.core.logging import pipeline_logger
from app.core.exceptions import GenerationError
from app.core.config import settings
from app.generation.parsing.json_utils import (
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

    async def call_ollama(self, prompt: str, temperature: float = 0.7) -> str:
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
                "format": "json",
                "options": {
                    "temperature": temperature,
                    "num_predict": 96,
                    "num_ctx": 2048,
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
            context_lines: List[str] = []
            for i, doc in enumerate(context, start=1):
                snippet = str(doc.get("snippet", "")).strip()
                context_lines.append(
                    (
                        f"[{i}] chunk_id={doc.get('chunk_id', 'unknown')} "
                        f"case_id={doc.get('case_id', 'unknown')} "
                        f"score={doc.get('score', doc.get('relevance_score', 0.0))}\n"
                        f"snippet={snippet[:120]}"
                    )
                )

            mode_hint = ""
            if mode == "force_json":
                mode_hint = (
                    "\n재요청 단계 2: 반드시 단일 JSON 객체만 출력하세요. "
                    "설명/주석/코드블록(```)은 절대 포함하지 마세요."
                )
            elif mode == "compact":
                mode_hint = (
                    "\n재요청 단계 3: 공백 최소화한 compact JSON 한 줄만 출력하세요. "
                    "추가 텍스트는 금지합니다."
                )

            prompt = (
                "검색 기반 QA입니다. 오직 JSON만 출력하세요.\n"
                "스키마: {\"answer\":\"string\",\"citations\":[{\"chunk_id\":\"string\",\"case_id\":\"string\",\"snippet\":\"string\",\"relevance_score\":0.0}],\"confidence\":\"low|medium|high\",\"limitations\":\"string\"}.\n"
                "주의: citations는 아래 근거 목록의 chunk_id/case_id/snippet만 사용하세요.\n\n"
                + mode_hint
                + "\n\n"
                f"질문: {query}\n\n"
                "검색 컨텍스트:\n"
                + "\n".join(context_lines)
            )

            return prompt
        except Exception as e:
            self.logger.error(f"프롬프트 구성 실패: {str(e)}")
            raise GenerationError(
                f"프롬프트 구성 실패: {str(e)}",
                code="PROCESSING_ERROR",
                retryable=False,
                details={"stage": "prompt"},
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

    async def generate_qa(
        self, query: str, context: List[Dict[str, Any]]
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
                "model": "qwen2.5:7b-instruct"
            }
        """
        try:
            self.logger.info(f"QA 응답 생성: query='{query}'")

            parsed: Dict[str, Any] = {}
            last_parse_error: GenerationError | None = None
            retry_steps = [
                {"stage": "preprocess", "mode": "default", "temperature": 0.3},
                {"stage": "force_json", "mode": "force_json", "temperature": 0.1},
                {"stage": "compact", "mode": "compact", "temperature": 0.0},
            ]
            retry_logs: List[Dict[str, Any]] = []

            for attempt_index, step in enumerate(retry_steps, start=1):
                try:
                    prompt = await self.build_rag_prompt(
                        query,
                        context,
                        mode=str(step["mode"]),
                    )
                    response_text = await self.call_ollama(
                        prompt,
                        temperature=float(step["temperature"]),
                    )
                    parsed = await self.parse_json_response(response_text)
                    break
                except GenerationError as e:
                    if not str(getattr(e, "code", "")).startswith("PARSE_"):
                        raise

                    last_parse_error = e
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
                self.logger.warning("QA JSON 파싱 재시도 소진")
                raise GenerationError(
                    "모델 응답을 JSON으로 파싱하지 못했습니다.",
                    code="PARSE_RETRY_EXHAUSTED",
                    retryable=False,
                    details={
                        "retry_count": len(retry_steps),
                        "stage": "decode",
                        "last_error_code": (
                            last_parse_error.code if last_parse_error else "PARSE_JSON_DECODE_ERROR"
                        ),
                        "attempts": retry_logs,
                    },
                )

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
                "model": self.model,
            }

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

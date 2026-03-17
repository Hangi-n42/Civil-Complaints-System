"""
생성 서비스 (Generation)

Week 1 기준선 구현:
- Ollama 호출
- JSON 파싱/재시도
- citation 포함 QA 응답 생성
"""

from __future__ import annotations

from typing import Dict, Any, List
import json
import httpx

from app.core.logging import pipeline_logger
from app.core.exceptions import GenerationError
from app.core.config import settings


class GenerationService:
    """생성 서비스"""

    def __init__(self):
        """초기화"""
        self.logger = pipeline_logger
        self.ollama_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.max_retries = settings.MAX_RETRY_COUNT

    def _extract_json_string(self, text: str) -> str:
        """응답 텍스트에서 JSON 블록을 추출한다."""
        if "```json" in text:
            return text.split("```json", maxsplit=1)[1].split("```", maxsplit=1)[0].strip()
        if "```" in text:
            return text.split("```", maxsplit=1)[1].split("```", maxsplit=1)[0].strip()
        return text.strip()

    def _normalize_confidence(self, value: Any) -> float:
        """confidence를 0~1 number로 정규화한다."""
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))

        if isinstance(value, str):
            lowered = value.strip().lower()
            mapping = {"low": 0.35, "medium": 0.65, "high": 0.85}
            if lowered in mapping:
                return mapping[lowered]
            try:
                return max(0.0, min(1.0, float(lowered)))
            except ValueError:
                return 0.5

        return 0.5

    def _build_fallback_answer(self, query: str, context: List[Dict[str, Any]]) -> str:
        """LLM 실패 시 사용할 안전한 폴백 답변."""
        if not context:
            return "검색 결과가 부족하여 답변 근거를 확보하지 못했습니다. 질의를 더 구체화해 다시 시도해 주세요."

        snippets = [item.get("snippet", "") for item in context[:2] if item.get("snippet")]
        if not snippets:
            return "검색된 민원 근거를 바탕으로 추가 확인이 필요합니다."

        joined = " ".join(snippets)
        return (
            "검색 근거를 기준으로 보면, 주요 이슈는 다음과 같습니다: "
            f"{joined[:220]}"
        )

    async def call_ollama(self, prompt: str, temperature: float = 0.7) -> str:
        """
        Ollama LLM 호출

        Args:
            prompt: 프롬프트
            temperature: 온도 파라미터 (0~1)

        Returns:
            생성된 텍스트
        """
        try:
            self.logger.info(f"Ollama 호출: model={self.model}, temp={temperature}")
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

            url = f"{self.ollama_url.rstrip('/')}/api/generate"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            data = response.json()
            text = str(data.get("response", "")).strip()
            if not text:
                raise GenerationError("Ollama 응답이 비어 있습니다.")

            return text
        except Exception as e:
            self.logger.error(f"Ollama 호출 실패: {str(e)}")
            raise GenerationError(f"Ollama 호출 실패: {str(e)}") from e

    async def build_rag_prompt(
        self, query: str, context: List[Dict[str, Any]]
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

            prompt = (
                "검색 기반 QA입니다. 오직 JSON만 출력하세요.\n"
                "스키마: {\"answer\":\"string\",\"citations\":[{\"chunk_id\":\"string\",\"case_id\":\"string\",\"snippet\":\"string\",\"relevance_score\":0.0}],\"confidence\":\"low|medium|high\",\"limitations\":\"string\"}.\n"
                "주의: citations는 아래 근거 목록의 chunk_id/case_id/snippet만 사용하세요.\n\n"
                f"질문: {query}\n\n"
                "검색 컨텍스트:\n"
                + "\n".join(context_lines)
            )

            return prompt
        except Exception as e:
            self.logger.error(f"프롬프트 구성 실패: {str(e)}")
            raise GenerationError(f"프롬프트 구성 실패: {str(e)}") from e

    async def parse_json_response(
        self, text: str, schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        JSON 응답 파싱

        Args:
            text: LLM이 생성한 텍스트
            schema: 기대하는 스키마

        Returns:
            파싱된 JSON 객체
        """
        try:
            self.logger.debug(f"JSON 응답 파싱")

            json_str = self._extract_json_string(text)

            # JSON 파싱
            result = json.loads(json_str)

            required = ["answer", "citations", "confidence", "limitations"]
            missing = [field for field in required if field not in result]
            if missing:
                raise GenerationError(f"필수 필드 누락: {', '.join(missing)}")

            if not isinstance(result.get("citations"), list):
                raise GenerationError("citations 필드는 배열이어야 합니다.")

            normalized_citations: List[Dict[str, Any]] = []
            for item in result.get("citations", []):
                if not isinstance(item, dict):
                    continue
                normalized_citations.append(
                    {
                        "chunk_id": str(item.get("chunk_id", "")),
                        "case_id": str(item.get("case_id", "")),
                        "snippet": str(item.get("snippet", "")),
                        "relevance_score": self._normalize_confidence(
                            item.get("relevance_score", 0.5)
                        ),
                    }
                )

            result["citations"] = normalized_citations
            result["confidence"] = self._normalize_confidence(result.get("confidence"))

            return result
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 실패: {str(e)}")
            # 재시도 로직은 generate_qa에서 처리
            raise GenerationError(f"JSON 파싱 실패: {str(e)}") from e
        except Exception as e:
            self.logger.error(f"응답 파싱 실패: {str(e)}")
            raise GenerationError(f"응답 파싱 실패: {str(e)}") from e

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
                citations.append(
                    {
                        "chunk_id": str(item.get("chunk_id", "")),
                        "case_id": str(item.get("case_id", "")),
                        "snippet": str(item.get("snippet", "")),
                        "relevance_score": self._normalize_confidence(
                            item.get("score", item.get("relevance_score", 0.5))
                        ),
                    }
                )

            return citations
        except Exception as e:
            self.logger.error(f"Citation 생성 실패: {str(e)}")
            raise GenerationError(f"Citation 생성 실패: {str(e)}") from e

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

            # RAG 프롬프트 구성
            prompt = await self.build_rag_prompt(query, context)

            parsed: Dict[str, Any] = {}
            last_error: Exception | None = None

            for attempt in range(1, self.max_retries + 1):
                try:
                    response_text = await self.call_ollama(prompt)
                    parsed = await self.parse_json_response(response_text, schema={})
                    break
                except GenerationError as e:
                    last_error = e
                    self.logger.warning(f"QA JSON 파싱 재시도 {attempt}/{self.max_retries}: {str(e)}")

            if not parsed:
                fallback_citations = await self.build_citations("", context)
                result = {
                    "question": query,
                    "answer": self._build_fallback_answer(query, context),
                    "confidence": 0.45,
                    "citations": fallback_citations,
                    "limitations": "모델 JSON 파싱이 불안정하여 폴백 답변이 제공되었습니다.",
                    "model": self.model,
                }
                self.logger.warning(
                    f"QA 폴백 응답 사용: {str(last_error) if last_error else 'unknown'}"
                )
                return result

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

        except Exception as e:
            self.logger.error(f"QA 응답 생성 실패: {str(e)}")
            raise GenerationError(f"QA 응답 생성 실패: {str(e)}") from e


# 싱글톤
_generation_service = None


def get_generation_service() -> GenerationService:
    """생성 서비스 인스턴스 반환"""
    global _generation_service
    if _generation_service is None:
        _generation_service = GenerationService()
    return _generation_service

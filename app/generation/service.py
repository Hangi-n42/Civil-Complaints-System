"""
생성 서비스 (Generation)

Ollama를 통한 LLM 호출, RAG 응답 생성, JSON 파싱, Citation을 담당한다.
"""

from typing import Dict, Any, List, Optional
import json
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
        self.max_retries = settings.MAX_RETRY_COUNT

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
            # TODO: Ollama API 호출 구현
            # - requests 또는 httpx 사용
            # - {model, prompt, temperature, stream=False} 파라미터
            response = ""
            return response
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

            # TODO: 프롬프트 템플릿 작성
            # - 시스템 역할 정의
            # - 컨텍스트 삽입
            # - 질문 삽입
            # - 응답 형식 지정

            prompt = f"""
다음은 민원 처리 시스템입니다.

질문: {query}

컨텍스트:
"""
            for i, doc in enumerate(context):
                prompt += f"\n{i + 1}. {doc.get('text', '')}"

            prompt += "\n\n위 정보를 바탕으로 답변해주세요."

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

            # JSON 추출 (```json ... ``` 형식 지원)
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0].strip()
            else:
                json_str = text

            # JSON 파싱
            result = json.loads(json_str)

            # TODO: 스키마 검증 로직 추가
            # - 필수 필드 확인
            # - 타입 검증

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

            # TODO: Citation 빌더 로직 구현
            # - 응답에서 컨텍스트 참조 추출
            # - 문서 ID와 단락 번호 매핑
            citations = []

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

            # LLM 호출
            response_text = await self.call_ollama(prompt)

            # Citation 생성
            citations = await self.build_citations(response_text, context)

            # 결과 구성
            result = {
                "question": query,
                "answer": response_text,
                "confidence": 0.8,  # TODO: 신뢰도 계산
                "citations": citations,
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

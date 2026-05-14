"""LLM 기반 4요소 시맨틱 추출기 (Stage 2)

Ollama EXAONE 3.0 (7.8B-Instruct) 를 사용해 민원 원문에서
observation / result / request / context 를 JSON으로 추출한다.

파싱 전략:
  1차 시도: temperature=0.1
  2차 시도: temperature=0.0 + 강화 프롬프트 (JSONDecodeError / ValidationError 시)
  Fallback: 빈 FourElementsLLMOutput (연결 불가 / 재시도 전부 실패)
"""

from __future__ import annotations

import json
import time
from typing import Optional, Tuple

import httpx
from pydantic import ValidationError

from app.core.logging import pipeline_logger
from app.structuring.schemas import FourElementsLLMOutput

_SYSTEM_PROMPT = """\
당신은 민원 분석 AI입니다.
사용자의 민원 텍스트를 읽고 다음 4가지 요소를 추출하여 JSON 형식으로만 반환하세요.
다른 텍스트, 설명, 코드블록은 출력하지 마세요.

추출 항목:
- observation: 민원인이 겪은 문제 상황이나 관찰한 사실 (없으면 null)
- result: 문제로 인해 발생한 현재의 결과나 피해 (없으면 null)
- request: 민원인이 행정기관에 요구하는 구체적인 조치 (없으면 null)
- context: 문제가 발생한 배경이나 부가 설명 (없으면 null)

출력 형식 (반드시 이 JSON 구조만 반환):
{"observation": "...", "result": "...", "request": "...", "context": "..."}\
"""

_RETRY_SUFFIX = "\n\n[중요] 반드시 순수 JSON 객체 하나만 출력하세요. 설명, 주석, 코드블록 없음."


class LLMSemanticExtractor:
    """Ollama 기반 4요소 추출기."""

    def __init__(
        self,
        ollama_url: str,
        model: str,
        timeout: float = 30.0,
        max_text_len: int = 2000,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_text_len = max_text_len
        self.logger = pipeline_logger

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, text: str, temperature: float, retry: bool) -> dict:
        system = _SYSTEM_PROMPT + (_RETRY_SUFFIX if retry else "")
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"민원 텍스트:\n{text[: self.max_text_len]}"},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": 512,
                "num_ctx": 4096,
            },
        }

    async def _call_once(
        self, text: str, temperature: float, retry: bool = False
    ) -> Optional[FourElementsLLMOutput]:
        """Ollama /api/chat 를 한 번 호출하고 Pydantic 모델로 검증 후 반환한다.

        /api/chat 은 Ollama 가 모델별 chat template 을 자동 적용하므로
        EXAONE 3.0 같은 instruct 모델에서 system 지시를 올바르게 처리한다.

        Returns None 이 아닌 FourElementsLLMOutput, 또는 파싱 실패 시 None.
        네트워크/타임아웃 예외는 호출부로 전파한다.
        """
        payload = self._build_payload(text, temperature, retry)
        url = f"{self.ollama_url}/api/chat"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            raw = str(
                response.json().get("message", {}).get("content", "")
            ).strip()

        if not raw:
            return None

        parsed = json.loads(raw)  # JSONDecodeError 는 호출부로 전파
        return FourElementsLLMOutput.model_validate(parsed)  # ValidationError 도 전파

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract(self, text: str) -> Tuple[FourElementsLLMOutput, int]:
        """4요소를 추출한다.

        Returns:
            (FourElementsLLMOutput, latency_ms)
            Fallback 시에도 예외 없이 빈 모델 반환.
        """
        started = time.monotonic()

        # 1차 시도 (temperature=0.1)
        try:
            result = await self._call_once(text, temperature=0.1)
            if result is not None:
                return result, int((time.monotonic() - started) * 1000)
        except (json.JSONDecodeError, ValidationError) as exc:
            self.logger.warning("LLM structuring parse failed (attempt 1): %s", exc)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            self.logger.warning(
                "LLM structuring: Ollama unreachable, using fallback. model=%s error=%s",
                self.model,
                exc,
            )
            return FourElementsLLMOutput(), int((time.monotonic() - started) * 1000)
        except (httpx.ReadTimeout, httpx.TimeoutException) as exc:
            self.logger.warning(
                "LLM structuring: Ollama timeout, using fallback. model=%s error=%s",
                self.model,
                exc,
            )
            return FourElementsLLMOutput(), int((time.monotonic() - started) * 1000)
        except Exception as exc:
            self.logger.warning("LLM structuring unexpected error (attempt 1): %s", exc)

        # 2차 시도 (temperature=0.0, 강화 프롬프트)
        try:
            result = await self._call_once(text, temperature=0.0, retry=True)
            if result is not None:
                return result, int((time.monotonic() - started) * 1000)
        except Exception as exc:
            self.logger.warning(
                "LLM structuring failed after retry, using fallback: %s", exc
            )

        return FourElementsLLMOutput(), int((time.monotonic() - started) * 1000)

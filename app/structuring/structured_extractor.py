"""① 스키마 제약 디코딩 추출기 — Track A.

Ollama `format=<JSON Schema>`(XGrammar)로 **형식을 수학적으로 보장**하고,
GoLLIE식 '가이드라인 임베딩' 프롬프트로 4요소 + 역할(민원인/유발자/조치객체)을 추출한다.

- 기존 LLMSemanticExtractor(자유 JSON)는 그대로 두고, 서비스에서 플래그로 교체한다(하위호환).
- 순수 부분(시스템 프롬프트·페이로드·파싱)은 모델 없이 테스트 가능.
- Ollama 미가용 시 빈 StructuredLLMOutput 로 안전 폴백.
"""

from __future__ import annotations

import json
import time
from typing import Optional, Tuple

import httpx
from pydantic import ValidationError

from app.core.logging import pipeline_logger
from app.structuring.schemas import StructuredLLMOutput, llm_output_json_schema

# GoLLIE식 가이드라인: 각 필드 정의 + 한국어 예시 + 규칙
SYSTEM_PROMPT = """\
당신은 부산시 민원 구조화 AI입니다. 민원 원문을 읽고 아래 항목을 추출해 지정된 JSON 스키마로만 출력합니다.
원문에 없는 내용은 절대 지어내지 말고, 해당 필드는 빈 문자열("")로 두세요. 모든 키를 반드시 채웁니다.

[4요소 — 없으면 ""]
- observation(관찰): 민원인이 겪은 문제 상황이나 관찰한 사실. 예) "가로등이 깜빡이다 꺼진다"
- result(결과): 그 문제로 발생한 피해·결과. 예) "밤에 길이 어두워 위험하다"
- request(요청): 행정기관에 요구하는 구체적 조치. 예) "가로등을 교체해 주세요"
- context(맥락): 배경·부가 설명. 예) "한 달 전부터 반복된다"

[result_status]
- result가 실제로 발생함 → "present"
- 아직 결과가 안 났고 우려 단계 → "pending"
- 정보가 부족해 판단 불가 → "insufficient"

[역할 — 원문 근거로만, 없으면 ""]
- complainant(민원인): 민원을 제기한 주체(보통 글쓴이: "저", "주민").
- respondent(유발자·대상): 문제를 일으킨 대상. 예) "옆집 공장". 가해 주체가 없으면 "".
- target_object(조치객체): 조치가 필요한 대상물·현상. 예) "가로등", "소음".

[규칙]
- 추측·창작 금지. 원문에 근거가 있는 것만.
- 스키마의 모든 키 출력(없으면 ""). JSON 외 다른 텍스트 금지.

[예시]
입력: "옆집 공장이 새벽마다 소음을 내서 잠을 못 잡니다. 단속해 주세요."
출력: {"observation":"옆집 공장이 새벽마다 소음을 낸다","result":"잠을 못 잔다","result_status":"present","request":"단속해 달라","context":"","complainant":"민원인(글쓴이)","respondent":"옆집 공장","target_object":"소음"}\
"""

_RETRY_SUFFIX = "\n\n[중요] 반드시 스키마의 모든 키를 가진 순수 JSON 하나만 출력하세요."


class StructuredExtractor:
    """제약 디코딩 기반 구조화 추출기."""

    def __init__(self, ollama_url: str, model: str, timeout: float = 30.0,
                 max_text_len: int = 2000) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_text_len = max_text_len
        self.logger = pipeline_logger

    # ── 순수: 프롬프트/페이로드/파싱 (테스트 가능) ───────────────────────
    def build_payload(self, text: str, temperature: float, retry: bool = False) -> dict:
        system = SYSTEM_PROMPT + (_RETRY_SUFFIX if retry else "")
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"민원 원문:\n{text[: self.max_text_len]}"},
            ],
            "stream": False,
            "format": llm_output_json_schema(),   # ← 자유 JSON이 아닌 '스키마' 제약
            "options": {"temperature": temperature, "num_predict": 512, "num_ctx": 4096},
        }

    @staticmethod
    def parse_content(raw: str) -> Optional[StructuredLLMOutput]:
        raw = (raw or "").strip()
        if not raw:
            return None
        parsed = json.loads(raw)            # JSONDecodeError → 호출부
        return StructuredLLMOutput.model_validate(parsed)  # ValidationError → 호출부

    # ── Ollama 호출 ──────────────────────────────────────────────────────
    async def _call_once(self, text: str, temperature: float, retry: bool = False
                         ) -> Optional[StructuredLLMOutput]:
        payload = self.build_payload(text, temperature, retry)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            raw = str(response.json().get("message", {}).get("content", "")).strip()
        return self.parse_content(raw)

    async def extract(self, text: str) -> Tuple[StructuredLLMOutput, int]:
        """구조화 추출. 실패/미가용 시 빈 StructuredLLMOutput 로 폴백."""
        started = time.monotonic()
        try:
            result = await self._call_once(text, temperature=0.1)
            if result is not None:
                return result, int((time.monotonic() - started) * 1000)
        except (json.JSONDecodeError, ValidationError) as exc:
            self.logger.warning("structured parse 실패(1차): %s", exc)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            self.logger.warning("Ollama 미가용, 폴백. model=%s err=%s", self.model, exc)
            return StructuredLLMOutput(), int((time.monotonic() - started) * 1000)
        except (httpx.ReadTimeout, httpx.TimeoutException) as exc:
            self.logger.warning("Ollama 타임아웃, 폴백. err=%s", exc)
            return StructuredLLMOutput(), int((time.monotonic() - started) * 1000)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("structured 예기치 못한 오류(1차): %s", exc)

        try:
            result = await self._call_once(text, temperature=0.0, retry=True)
            if result is not None:
                return result, int((time.monotonic() - started) * 1000)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("structured 재시도 실패, 폴백: %s", exc)

        return StructuredLLMOutput(), int((time.monotonic() - started) * 1000)

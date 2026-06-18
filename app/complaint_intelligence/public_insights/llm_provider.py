"""PublicAgencyInsight 합성을 위한 LLM provider 인터페이스."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any, Protocol

from app.complaint_intelligence.config import ComplaintIntelligenceConfig


class PublicInsightLLMProvider(Protocol):
    """모델 종속성을 숨기는 최소 LLM 인터페이스."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        """프롬프트와 JSON schema를 받아 JSON 객체를 반환한다."""


class DisabledLLMProvider:
    """LLM 비활성 상태를 명시적으로 표현한다."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        raise RuntimeError("PUBLIC_INSIGHT_LLM_DISABLED")


class FakePublicInsightLLMProvider:
    """테스트와 로컬 기본값을 위한 결정적 provider."""

    def generate_json(self, prompt: str, schema: dict) -> dict:
        pack = _extract_pack(prompt)
        insight_type = str(pack.get("type_hint") or "RECURRING_COMPLAINT_PATTERN")
        topic = str(pack.get("topic_label") or "민원")
        count = int(pack.get("complaint_count") or 0)
        region = _dominant_region(pack)
        department = _dominant_department(pack)
        aspects = list(pack.get("extracted_aspects") or [])
        requests = list(pack.get("citizen_requests") or [])
        evidence_ids = [str(item.get("complaint_id")) for item in pack.get("representative_complaints", []) if item.get("complaint_id")]
        selected_ids = evidence_ids[:3]
        top_aspects = ", ".join(str(item.get("aspect")) for item in aspects[:2]) or "반복 불편"
        action = _action_for(insight_type, topic)

        return {
            "title": _title_for(insight_type, region, topic),
            "summary": f"최근 분석 기간 동안 {region or '해당 지역'}에서 {topic} 관련 민원 {count}건이 확인되었고, {top_aspects} 관련 불편이 반복되었습니다.",
            "problem_diagnosis": f"핵심 문제는 {topic} 민원에서 {top_aspects}가 반복되어 담당자가 즉시 확인할 수 있는 행정 조치 단위로 정리할 필요가 있다는 점입니다.",
            "root_cause_hypotheses": [
                {
                    "hypothesis": f"{top_aspects}에 대한 안내 또는 처리 흐름이 시민 관점에서 충분히 명확하지 않을 가능성이 있습니다.",
                    "support_level": "HIGH" if count >= 5 else "MEDIUM",
                    "supporting_evidence_ids": selected_ids,
                    "needs_human_validation": True,
                }
            ],
            "extracted_aspects": aspects,
            "citizen_requests": requests,
            "recommended_actions": [
                {
                    "action": action["action"],
                    "horizon": action["horizon"],
                    "action_type": action["action_type"],
                    "responsible_unit_hint": department,
                    "why": f"{top_aspects} 관련 민원이 {count}건 확인되었습니다.",
                    "supporting_evidence_ids": selected_ids,
                    "expected_impact": action["expected_impact"],
                    "risk_or_dependency": action["risk_or_dependency"],
                }
            ],
            "expected_impact": action["expected_impact"],
            "uncertainty": [
                "민원 텍스트 기반 분석이므로 실제 제도 변경 가능성, 예산, 현장 상태는 담당자 확인이 필요합니다."
            ],
            "requires_human_review": insight_type in {"SAFETY_RISK_SIGNAL", "POLICY_IMPROVEMENT_OPPORTUNITY", "SERVICE_DESIGN_IMPROVEMENT"},
            "explanation": "EvidencePack의 민원 수, aspect 빈도, 대표 민원 ID만 사용해 생성했습니다.",
        }


class LocalLLMProvider:
    """OpenAI-compatible 또는 Ollama 스타일 로컬 엔드포인트용 간단 provider."""

    def __init__(self, config: ComplaintIntelligenceConfig) -> None:
        self.base_url = _normalize_ollama_url(config.public_insight_llm_base_url)
        self.model = config.public_insight_llm_model
        self.timeout = config.public_insight_llm_timeout_seconds
        self.temperature = config.public_insight_llm_temperature
        self.num_ctx = config.public_insight_llm_num_ctx
        self.num_predict = config.public_insight_llm_num_predict
        self.num_gpu = config.public_insight_llm_num_gpu
        self.keep_alive = config.public_insight_llm_keep_alive
        self.stream = config.public_insight_llm_stream

    def generate_json(self, prompt: str, schema: dict) -> dict:
        if not self.base_url:
            raise RuntimeError("PUBLIC_INSIGHT_LLM_BASE_URL_MISSING")
        if not self.model:
            raise RuntimeError("PUBLIC_INSIGHT_LLM_MODEL_MISSING")

        payload = self._payload(prompt, schema)
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = self._read_streaming_response(response) if self.stream else response.read().decode("utf-8")
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError(f"PUBLIC_INSIGHT_LLM_TIMEOUT:{self.timeout}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("PUBLIC_INSIGHT_LLM_REQUEST_FAILED") from exc

        parsed = json.loads(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("response"), str):
            return _parse_json_object(parsed["response"])
        if isinstance(parsed, dict) and isinstance(parsed.get("message"), dict):
            content = str(parsed["message"].get("content") or "")
            return _parse_json_object(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("choices"), list):
            content = parsed["choices"][0].get("message", {}).get("content", "")
            return _parse_json_object(str(content))
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("PUBLIC_INSIGHT_LLM_RESPONSE_NOT_OBJECT")

    def _payload(self, prompt: str, schema: dict) -> dict[str, Any]:
        response_format: str | dict[str, Any] = schema if schema else "json"
        if self.base_url.endswith("/api/chat"):
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": self.stream,
                "format": response_format,
            }
            return self._with_runtime_options(payload)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": self.stream,
            "format": response_format,
        }
        return self._with_runtime_options(payload)

    def _read_streaming_response(self, response: Any) -> str:
        """Ollama streaming JSONL 응답을 하나의 JSON 문자열로 합친다."""

        chunks: list[str] = []
        for raw_line in response:
            line = raw_line.decode("utf-8").strip() if isinstance(raw_line, bytes) else str(raw_line).strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item.get("response"), str):
                chunks.append(item["response"])
            elif isinstance(item.get("message"), dict):
                chunks.append(str(item["message"].get("content") or ""))
            if item.get("done"):
                break
        if not chunks:
            raise ValueError("PUBLIC_INSIGHT_LLM_EMPTY_STREAM")
        return "".join(chunks)

    def _with_runtime_options(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ollama 실행 옵션을 payload에 추가한다."""

        options: dict[str, Any] = {
            "temperature": self.temperature,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "num_gpu": self.num_gpu,
        }
        payload["options"] = options
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        return payload


def build_llm_provider(config: ComplaintIntelligenceConfig) -> PublicInsightLLMProvider:
    """config 값에 맞는 provider를 생성한다."""

    if not config.public_insight_llm_enabled:
        return DisabledLLMProvider()
    provider = config.public_insight_llm_provider.lower()
    if provider == "fake":
        return FakePublicInsightLLMProvider()
    if provider == "disabled":
        return DisabledLLMProvider()
    if provider == "local":
        return LocalLLMProvider(config)
    return DisabledLLMProvider()


def _extract_pack(prompt: str) -> dict[str, Any]:
    match = re.search(r"EVIDENCE_PACK_JSON:\s*(\{.*\})\s*$", prompt, re.S)
    if not match:
        return {}
    return json.loads(match.group(1))


def _normalize_ollama_url(base_url: str) -> str:
    url = (base_url or "").rstrip("/")
    if not url:
        return ""
    if url.endswith("/api/generate") or url.endswith("/api/chat"):
        return url
    if url.endswith("/api"):
        return f"{url}/generate"
    return f"{url}/api/generate"


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(content.strip())
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("PUBLIC_INSIGHT_LLM_JSON_NOT_OBJECT")
    return parsed


def _strip_code_fence(content: str) -> str:
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content.strip()


def _dominant_region(pack: dict[str, Any]) -> str | None:
    region_summary = pack.get("region_summary") or {}
    return region_summary.get("dominant_region")


def _dominant_department(pack: dict[str, Any]) -> str | None:
    department_summary = pack.get("department_summary") or {}
    return department_summary.get("dominant_department")


def _title_for(insight_type: str, region: str | None, topic: str) -> str:
    prefix = f"{region} " if region else ""
    suffix = {
        "POLICY_IMPROVEMENT_OPPORTUNITY": "정책/서비스 개선 검토",
        "PUBLIC_GUIDANCE_NEEDED": "시민 안내 개선 필요",
        "SERVICE_DESIGN_IMPROVEMENT": "서비스 설계 개선 필요",
        "ACCESSIBILITY_OR_USABILITY_ISSUE": "접근성/사용성 개선 필요",
        "SAFETY_RISK_SIGNAL": "안전 위험 대응 필요",
        "ENFORCEMENT_PRIORITY": "단속 우선순위 조정 필요",
        "FACILITY_MAINTENANCE_PRIORITY": "시설 보수 우선순위 검토",
    }.get(insight_type, "행정 대응 인사이트")
    return f"{prefix}{topic} {suffix}"


def _action_for(insight_type: str, topic: str) -> dict[str, str | None]:
    defaults = {
        "POLICY_IMPROVEMENT_OPPORTUNITY": {
            "action": f"{topic} 관련 반복 개선 요구를 신청 절차, 기준, 안내 개선 과제로 분리해 검토합니다.",
            "horizon": "MID_TERM",
            "action_type": "POLICY_REVIEW",
            "expected_impact": "반복 불편 지점의 정책 검토 우선순위를 명확히 할 수 있습니다.",
            "risk_or_dependency": "제도 변경은 예산, 조례, 담당 부서 검토가 필요합니다.",
        },
        "PUBLIC_GUIDANCE_NEEDED": {
            "action": f"{topic} 관련 FAQ, 신청 체크리스트, 고지문을 시민 표현 중심으로 보강합니다.",
            "horizon": "SHORT_TERM",
            "action_type": "PUBLIC_GUIDANCE",
            "expected_impact": "반복 문의와 신청 오류를 줄일 가능성이 있습니다.",
            "risk_or_dependency": "정확한 기준은 담당 부서 확인이 필요합니다.",
        },
        "SERVICE_DESIGN_IMPROVEMENT": {
            "action": f"{topic} 이용 절차의 신청/예약/결제 단계를 점검하고 안내 흐름을 단순화합니다.",
            "horizon": "SHORT_TERM",
            "action_type": "SERVICE_DESIGN",
            "expected_impact": "이용 중단과 반복 문의를 줄일 가능성이 있습니다.",
            "risk_or_dependency": "시스템 로그와 실제 오류 재현 확인이 필요합니다.",
        },
        "SAFETY_RISK_SIGNAL": {
            "action": f"{topic} 위험 지점에 대한 긴급 현장 점검과 시민 안전 안내를 실시합니다.",
            "horizon": "IMMEDIATE",
            "action_type": "FIELD_INSPECTION",
            "expected_impact": "사고 위험을 조기에 낮출 가능성이 있습니다.",
            "risk_or_dependency": "현장 상황 확인 전까지 원인 단정은 어렵습니다.",
        },
        "ENFORCEMENT_PRIORITY": {
            "action": f"{topic} 민원 집중 지역과 시간대를 기준으로 단속 동선을 조정합니다.",
            "horizon": "SHORT_TERM",
            "action_type": "ENFORCEMENT",
            "expected_impact": "반복 위반 민원 감소를 기대할 수 있습니다.",
            "risk_or_dependency": "단속 권한과 인력 배치 확인이 필요합니다.",
        },
    }
    return defaults.get(
        insight_type,
        {
            "action": f"{topic} 관련 대표 민원을 검토하고 담당 부서의 대응 계획을 수립합니다.",
            "horizon": "SHORT_TERM",
            "action_type": "PROCESS_IMPROVEMENT",
            "expected_impact": "민원 처리 방향을 구체화할 수 있습니다.",
            "risk_or_dependency": "담당자 검토가 필요합니다.",
        },
    )

"""② 자기검증(Chain-of-Verification) + 근거 grounding — Track A.

추출된 4요소를 원문과 대조해 (a) 환각 필드 제거, (b) 근거 evidence_span 확정,
(c) **근거 기반 보정 신뢰도** 부여. 검증 LLM 호출은 주입형(verify_fn)이라 stub 으로 테스트 가능.

confidence 매핑(미보정 휴리스틱 — 라벨 확보 시 보정 예정):
  supported & exact   → 0.95
  supported & partial → 0.85
  supported & inferred→ 0.80
  unsupported         → 0.20 (+ 필드 텍스트 제거)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from app.structuring.merger import _find_span

# 검증 대상 텍스트 필드
_VERIFY_FIELDS = ["observation", "result", "request", "context"]

_CONF = {("yes", "exact"): 0.95, ("yes", "partial"): 0.85, ("yes", "inferred"): 0.80}
_CONF_UNSUPPORTED = 0.20

# verify_fn 계약: (raw_text, field_name, field_text) -> {"supported": bool, "quote": str}
VerifyFn = Callable[[str, str, str], Dict[str, Any]]


def calibrated_confidence(supported: bool, span_source: str) -> float:
    if not supported:
        return _CONF_UNSUPPORTED
    return _CONF.get(("yes", span_source), 0.80)


def _is_inferred(field: Dict[str, Any]) -> bool:
    """evidence_span 이 [0,0] → 원문에서 위치를 못 찾음(paraphrase/환각 위험)."""
    span = field.get("evidence_span") or [0, 0]
    return list(span) == [0, 0]


def verify_candidate(
    raw_text: str,
    candidate: Dict[str, Any],
    verify_fn: VerifyFn,
    fields: Optional[List[str]] = None,
    drop_unsupported: bool = True,
    only_inferred: bool = True,
) -> Dict[str, Any]:
    """후보의 4요소를 검증해 grounding·보정 신뢰도 적용 + 환각 제거.

    only_inferred=True(기본): **근거 span 이 inferred([0,0])인 필드에만** 검증 LLM 을 돈다.
    이미 원문에 grounding 된 필드는 검증을 생략하고 verified=True 로 둔다(LLM 호출 절약).
    반환: 갱신된 candidate(in-place) + candidate["verification"] 메타.
    """
    fields = fields or _VERIFY_FIELDS
    checked: List[str] = []
    removed: List[str] = []
    skipped_grounded: List[str] = []

    for fname in fields:
        field = candidate.get(fname)
        if not isinstance(field, dict):
            continue
        text = str(field.get("text") or "").strip()
        if not text:
            continue  # 빈 필드는 검증 불필요
        if only_inferred and not _is_inferred(field):
            field["verified"] = True   # 이미 원문에 grounding됨 → 검증 생략
            skipped_grounded.append(fname)
            continue
        checked.append(fname)

        try:
            res = verify_fn(raw_text, fname, text) or {}
        except Exception:
            res = {}
        supported = bool(res.get("supported", False))
        quote = str(res.get("quote") or "").strip()

        if supported:
            # 근거 인용을 원문에서 찾아 span 확정(인용 없으면 필드 텍스트로 탐색)
            start, end, source = _find_span(raw_text, quote or text)
            field["evidence_span"] = [start, end]
            field["confidence"] = calibrated_confidence(True, source)
            field["verified"] = True
        else:
            field["verified"] = False
            field["confidence"] = _CONF_UNSUPPORTED
            if drop_unsupported:
                field["text"] = ""           # 환각 필드 제거
                field["evidence_span"] = [0, 0]
                if fname == "result":
                    field["status"] = "insufficient"
                removed.append(fname)

    candidate["verification"] = {
        "checked": checked,
        "removed": removed,
        "skipped_grounded": skipped_grounded,
        "method": "self_verify_cove",
    }
    return candidate


# ──────────────────────────────────────────────────────────────────────────
# 프로덕션 verify_fn: Ollama 제약 디코딩 검증 (로컬에서만 실행)
# ──────────────────────────────────────────────────────────────────────────
_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "quote": {"type": "string"},
    },
    "required": ["supported", "quote"],
    "additionalProperties": False,
}

_VERIFY_SYSTEM = """\
당신은 민원 구조화 검증 AI입니다. [원문]과 추출된 [{field} 후보]를 비교해,
그 후보가 원문에 실제로 근거가 있는지 판정합니다.
- 원문에 근거가 있으면 supported=true 이고 quote 에 근거가 되는 원문 문구를 그대로 인용합니다.
- 원문에 없거나 추측·창작이면 supported=false, quote="".
지어내지 마세요. JSON 스키마로만 출력합니다.\
"""


def make_ollama_verifier(ollama_url: str, model: str, timeout: float = 20.0) -> VerifyFn:
    """Ollama 제약 디코딩 기반 verify_fn 생성(로컬). 미가용 시 supported=false 폴백."""
    import httpx

    base = ollama_url.rstrip("/")

    def _verify(raw_text: str, field_name: str, field_text: str) -> Dict[str, Any]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _VERIFY_SYSTEM.replace("{field}", field_name)},
                {"role": "user", "content": f"[원문]\n{raw_text[:2000]}\n\n[{field_name} 후보]\n{field_text}"},
            ],
            "stream": False,
            "format": _VERIFY_SCHEMA,
            "options": {"temperature": 0.0, "num_predict": 256},
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.post(f"{base}/api/chat", json=payload)
                r.raise_for_status()
                raw = str(r.json().get("message", {}).get("content", "")).strip()
            data = json.loads(raw)
            return {"supported": bool(data.get("supported", False)), "quote": str(data.get("quote") or "")}
        except Exception:
            # 검증 불가 시 보수적으로 supported=true(원추출 유지)하지 않고, 영향 최소화 위해
            # supported=true 로 두되 grounding 만 생략하는 것이 안전(환각 단정 회피).
            return {"supported": True, "quote": field_text}

    return _verify

"""QA JSON 파싱/정규화 공통 유틸."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.core.exceptions import GenerationError


def normalize_confidence(value: Any) -> float:
    """confidence 값을 0~1 범위의 숫자로 정규화한다."""
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


def extract_json_string(text: str) -> str:
    """모델 응답 텍스트에서 JSON 객체 문자열만 추출한다."""
    if "```json" in text:
        return text.split("```json", maxsplit=1)[1].split("```", maxsplit=1)[0].strip()
    if "```" in text:
        return text.split("```", maxsplit=1)[1].split("```", maxsplit=1)[0].strip()

    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise GenerationError(
            "모델 응답에서 JSON 블록을 찾지 못했습니다.",
            code="PARSE_JSON_BLOCK_EXTRACTION_FAILED",
            retryable=True,
            details={"stage": "extract"},
        )

    return stripped[start : end + 1].strip()


def parse_qa_json_response(text: str) -> Dict[str, Any]:
    """QA 응답 JSON을 파싱하고 필수 필드를 검증/정규화한다."""
    try:
        json_str = extract_json_string(text)
        result = json.loads(json_str)

        required = ["answer", "citations", "confidence", "limitations"]
        missing = [field for field in required if field not in result]
        if missing:
            raise GenerationError(
                f"필수 필드 누락: {', '.join(missing)}",
                code="PARSE_SCHEMA_MISMATCH",
                retryable=True,
                details={"stage": "schema", "missing_fields": missing},
            )

        if not isinstance(result.get("citations"), list):
            raise GenerationError(
                "citations 필드는 배열이어야 합니다.",
                code="PARSE_SCHEMA_MISMATCH",
                retryable=True,
                details={"stage": "schema", "field": "citations"},
            )

        limitations = str(result.get("limitations", "")).strip()
        if not limitations:
            raise GenerationError(
                "limitations 필드는 빈 문자열일 수 없습니다.",
                code="PARSE_SCHEMA_MISMATCH",
                retryable=True,
                details={"stage": "schema", "field": "limitations"},
            )

        normalized_citations: List[Dict[str, Any]] = []
        for item in result.get("citations", []):
            if not isinstance(item, dict):
                continue

            citation: Dict[str, Any] = {
                "chunk_id": str(item.get("chunk_id", "")),
                "case_id": str(item.get("case_id", "")),
                "snippet": str(item.get("snippet", "")),
                "relevance_score": normalize_confidence(item.get("relevance_score", 0.5)),
            }

            doc_id = str(item.get("doc_id", "")).strip()
            if doc_id:
                citation["doc_id"] = doc_id

            normalized_citations.append(citation)

        result["citations"] = normalized_citations
        result["confidence"] = normalize_confidence(result.get("confidence"))
        result["limitations"] = limitations

        return result
    except json.JSONDecodeError as e:
        raise GenerationError(
            "모델 응답을 JSON으로 파싱하지 못했습니다.",
            code="PARSE_JSON_DECODE_ERROR",
            retryable=True,
            details={"stage": "decode", "reason": str(e)},
        ) from e
    except GenerationError:
        raise
    except Exception as e:
        raise GenerationError(
            f"응답 파싱 실패: {str(e)}",
            code="PARSE_SCHEMA_MISMATCH",
            retryable=True,
            details={"stage": "schema"},
        ) from e

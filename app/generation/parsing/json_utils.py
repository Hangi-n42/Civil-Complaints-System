"""QA JSON 파싱/정규화 공통 유틸."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.core.exceptions import GenerationError


def build_qa_response_schema(
    context: List[Dict[str, Any]],
    *,
    citations_max: int = 3,
) -> Dict[str, Any]:
    """Build an Ollama constrained-decoding schema from retrieved evidence."""
    evidence = [item for item in context if isinstance(item, dict)]
    chunk_ids = list(
        dict.fromkeys(str(item.get("chunk_id") or "").strip() for item in evidence)
    )
    case_ids = list(
        dict.fromkeys(str(item.get("case_id") or "").strip() for item in evidence)
    )
    snippets = list(
        dict.fromkeys(str(item.get("snippet") or "").strip() for item in evidence)
    )
    chunk_ids = [value for value in chunk_ids if value]
    case_ids = [value for value in case_ids if value]
    snippets = [value for value in snippets if value]

    def evidence_string_schema(values: List[str]) -> Dict[str, Any]:
        schema: Dict[str, Any] = {"type": "string", "minLength": 1}
        if values:
            schema["enum"] = values
        return schema

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["citations", "answer", "limitations", "structured_output"],
        "properties": {
            "citations": {
                "type": "array",
                "minItems": 1,
                "maxItems": max(1, min(int(citations_max), len(evidence) or 1)),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "chunk_id",
                        "case_id",
                        "snippet",
                        "relevance_score",
                    ],
                    "properties": {
                        "chunk_id": evidence_string_schema(chunk_ids),
                        "case_id": evidence_string_schema(case_ids),
                        "snippet": evidence_string_schema(snippets),
                        "relevance_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
            },
            "answer": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1600,
                "description": (
                    "Korean civil-affairs reply only. Do not include JSON key names, "
                    "Markdown, citations metadata, or text after the official closing."
                ),
            },
            "limitations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "string", "minLength": 1},
            },
            "structured_output": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "action_items", "request_segments"],
                "properties": {
                    "summary": {"type": "string", "minLength": 1},
                    "action_items": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 3,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "request_segments": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {"type": "string"},
                    },
                },
            },
        },
    }


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


def _schema_error(
    message: str,
    *,
    field: str = "",
    missing_fields: List[str] | None = None,
    unexpected_fields: List[str] | None = None,
) -> GenerationError:
    details: Dict[str, Any] = {"stage": "schema"}
    if field:
        details["field"] = field
    if missing_fields:
        details["missing_fields"] = missing_fields
    if unexpected_fields:
        details["unexpected_fields"] = unexpected_fields
    return GenerationError(
        message,
        code="PARSE_SCHEMA_MISMATCH",
        retryable=True,
        details=details,
    )


def validate_qa_payload_schema(payload: Any) -> Dict[str, Any]:
    """Validate the model payload against PromptFactory's public QA schema."""
    if not isinstance(payload, dict):
        raise _schema_error("모델 응답 JSON은 객체여야 합니다.", field="root")

    required = {"answer", "citations", "limitations", "structured_output"}
    missing = sorted(required - set(payload))
    unexpected = sorted(set(payload) - required)
    if missing or unexpected:
        parts = []
        if missing:
            parts.append(f"필수 필드 누락: {', '.join(missing)}")
        if unexpected:
            parts.append(f"허용되지 않은 필드: {', '.join(unexpected)}")
        raise _schema_error(
            "; ".join(parts),
            missing_fields=missing,
            unexpected_fields=unexpected,
        )

    answer = str(payload.get("answer") or "").strip()
    if not answer:
        raise _schema_error("answer 필드는 비어 있을 수 없습니다.", field="answer")

    raw_citations = payload.get("citations")
    if not isinstance(raw_citations, list) or not raw_citations:
        raise _schema_error(
            "citations 필드는 1개 이상의 객체를 가진 배열이어야 합니다.",
            field="citations",
        )

    normalized_citations: List[Dict[str, Any]] = []
    citation_required = {"chunk_id", "case_id", "snippet", "relevance_score"}
    citation_allowed = citation_required | {"doc_id"}
    for index, item in enumerate(raw_citations):
        if not isinstance(item, dict):
            raise _schema_error(
                f"citations[{index}]는 객체여야 합니다.",
                field=f"citations[{index}]",
            )
        item_missing = sorted(citation_required - set(item))
        item_unexpected = sorted(set(item) - citation_allowed)
        if item_missing or item_unexpected:
            raise _schema_error(
                f"citations[{index}] 스키마가 올바르지 않습니다.",
                field=f"citations[{index}]",
                missing_fields=item_missing,
                unexpected_fields=item_unexpected,
            )
        chunk_id = str(item.get("chunk_id") or "").strip()
        case_id = str(item.get("case_id") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        score = item.get("relevance_score")
        if not chunk_id or not case_id or not snippet:
            raise _schema_error(
                f"citations[{index}]의 문자열 필드는 비어 있을 수 없습니다.",
                field=f"citations[{index}]",
            )
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise _schema_error(
                f"citations[{index}].relevance_score는 숫자여야 합니다.",
                field=f"citations[{index}].relevance_score",
            )
        if not 0.0 <= float(score) <= 1.0:
            raise _schema_error(
                f"citations[{index}].relevance_score는 0과 1 사이여야 합니다.",
                field=f"citations[{index}].relevance_score",
            )
        citation: Dict[str, Any] = {
            "chunk_id": chunk_id,
            "case_id": case_id,
            "snippet": snippet,
            "relevance_score": float(score),
        }
        doc_id = str(item.get("doc_id") or "").strip()
        if doc_id:
            citation["doc_id"] = doc_id
        normalized_citations.append(citation)

    raw_limitations = payload.get("limitations")
    if isinstance(raw_limitations, list):
        limitation_parts = [
            str(item).strip() for item in raw_limitations if str(item).strip()
        ]
        if not limitation_parts or len(limitation_parts) != len(raw_limitations):
            raise _schema_error(
                "limitations 배열에는 비어 있지 않은 문자열만 사용할 수 있습니다.",
                field="limitations",
            )
        limitations = " / ".join(limitation_parts)
    elif isinstance(raw_limitations, str) and raw_limitations.strip():
        limitations = raw_limitations.strip()
    else:
        raise _schema_error(
            "limitations는 비어 있지 않은 문자열 또는 문자열 배열이어야 합니다.",
            field="limitations",
        )

    structured = payload.get("structured_output")
    structured_required = {"summary", "action_items", "request_segments"}
    if not isinstance(structured, dict):
        raise _schema_error(
            "structured_output은 객체여야 합니다.",
            field="structured_output",
        )
    structured_missing = sorted(structured_required - set(structured))
    structured_unexpected = sorted(set(structured) - structured_required)
    if structured_missing or structured_unexpected:
        raise _schema_error(
            "structured_output 스키마가 올바르지 않습니다.",
            field="structured_output",
            missing_fields=structured_missing,
            unexpected_fields=structured_unexpected,
        )
    summary = str(structured.get("summary") or "").strip()
    action_items = structured.get("action_items")
    request_segments = structured.get("request_segments")
    if not summary:
        raise _schema_error(
            "structured_output.summary는 비어 있을 수 없습니다.",
            field="structured_output.summary",
        )
    if (
        not isinstance(action_items, list)
        or len(action_items) < 2
        or any(not isinstance(item, str) or not item.strip() for item in action_items)
    ):
        raise _schema_error(
            "structured_output.action_items에는 2개 이상의 비어 있지 않은 문자열이 필요합니다.",
            field="structured_output.action_items",
        )
    if not isinstance(request_segments, list) or any(
        not isinstance(item, str) for item in request_segments
    ):
        raise _schema_error(
            "structured_output.request_segments는 문자열 배열이어야 합니다.",
            field="structured_output.request_segments",
        )

    return {
        "answer": answer,
        "citations": normalized_citations,
        "limitations": limitations,
        "structured_output": {
            "summary": summary,
            "action_items": [item.strip() for item in action_items],
            "request_segments": [item.strip() for item in request_segments],
        },
        "confidence": 0.5,
    }


def parse_qa_json_response(text: str) -> Dict[str, Any]:
    """QA 응답 JSON을 파싱하고 필수 필드를 검증/정규화한다."""
    try:
        json_str = extract_json_string(text)
        return validate_qa_payload_schema(json.loads(json_str))
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

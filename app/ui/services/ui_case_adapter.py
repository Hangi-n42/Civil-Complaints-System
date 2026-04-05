"""UI Queue 전용 케이스 포맷 어댑터."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.core.title_builder import build_case_title

_UI_CATEGORY_ALLOWED = {"도로안전", "환경위생", "주거복지", "교통행정", "기타"}
_UI_CATEGORY_MAP = {
    "문화관광": "기타",
}
_UNKNOWN_REGION_VALUES = {"unknown", "Unknown", "UNK", "", "-", "None", "none"}


def _format_received_at(value: Any) -> str:
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", ""))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value
    return "-"


def normalize_ui_category(category_norm: Any, category_raw: Any) -> str:
    norm = str(category_norm or "").strip()
    raw = str(category_raw or "").strip()

    candidate = norm or raw
    if not candidate:
        return "기타"

    mapped = _UI_CATEGORY_MAP.get(candidate, candidate)
    if mapped in _UI_CATEGORY_ALLOWED:
        return mapped
    return "기타"


def normalize_ui_region(region_norm: Any, region_raw: Any) -> str:
    norm = str(region_norm or "").strip()
    raw = str(region_raw or "").strip()

    candidate = norm or raw
    if candidate in _UNKNOWN_REGION_VALUES:
        return "-"
    return candidate or "-"


def _span_to_evidence_text(raw_text: str, span: Any) -> str:
    if isinstance(span, str):
        return span
    if (
        isinstance(span, (list, tuple))
        and len(span) == 2
        and isinstance(span[0], int)
        and isinstance(span[1], int)
    ):
        start, end = span
        if isinstance(raw_text, str) and 0 <= start < end <= len(raw_text):
            return raw_text[start:end]
        return f"{start}:{end}"
    return ""


def _pack_field(structured_src: Dict[str, Any], raw_text: str, name: str) -> Dict[str, Any]:
    field = structured_src.get(name) if isinstance(structured_src.get(name), dict) else {}
    text = str(field.get("text", ""))
    confidence = float(field.get("confidence", 0.0) or 0.0)
    span = field.get("evidence_span")
    evidence_text = _span_to_evidence_text(raw_text, span)
    return {"text": text, "confidence": confidence, "evidence_span": evidence_text}


def _field_text(structured_src: Dict[str, Any], name: str) -> str:
    field = structured_src.get(name)
    if isinstance(field, dict):
        return str(field.get("text", "")).strip()
    return ""


def to_ui_queue_case(item: Dict[str, Any], index: int) -> Dict[str, Any]:
    raw_text = str(item.get("raw_text") or item.get("text") or "")

    structured_in = item.get("structured") if isinstance(item.get("structured"), dict) else None
    structured_src = structured_in if structured_in is not None else item

    validation = (
        structured_src.get("validation")
        if isinstance(structured_src.get("validation"), dict)
        else {}
    )
    is_valid = bool(validation.get("is_valid", True))

    entities_in = structured_src.get("entities") if isinstance(structured_src.get("entities"), list) else []
    entities: List[Dict[str, Any]] = []
    for entity in entities_in:
        if not isinstance(entity, dict):
            continue
        label = entity.get("label")
        text = entity.get("text")
        if not label or not text:
            continue
        entities.append({"label": str(label), "text": str(text)})

    case_id = str(item.get("case_id", "")) or f"SAMPLE-{index:03d}"
    category_raw = str(item.get("category") or "")
    region_raw = str(item.get("region") or "")

    category = normalize_ui_category(item.get("category_norm"), category_raw)
    region = normalize_ui_region(item.get("region_norm"), region_raw)

    assignee = str(item.get("assignee") or item.get("source") or "미지정")
    priority = str(item.get("priority") or "보통")
    status = str(item.get("status") or "미처리")
    received_at_raw = item.get("received_at") or item.get("created_at")
    title = build_case_title(
        explicit_title=item.get("title"),
        observation=_field_text(structured_src, "observation"),
        request=_field_text(structured_src, "request"),
        raw_text=raw_text,
        category=category,
    )

    return {
        "case_id": case_id,
        "title": title,
        "received_at": _format_received_at(received_at_raw),
        "priority": priority,
        "status": status,
        "assignee": assignee,
        "raw_text": raw_text,
        "category": category,
        "category_norm": category,
        "category_raw": category_raw,
        "region": region,
        "region_norm": region,
        "region_raw": region_raw,
        "structured": {
            "observation": _pack_field(structured_src, raw_text, "observation"),
            "result": _pack_field(structured_src, raw_text, "result"),
            "request": _pack_field(structured_src, raw_text, "request"),
            "context": _pack_field(structured_src, raw_text, "context"),
            "entities": entities,
            "is_valid": is_valid,
            "schema_version": str(structured_src.get("schema_version") or "1.0"),
        },
    }


def load_ui_cases_from_week2_sample(sample_path: Path) -> List[Dict[str, Any]]:
    if not sample_path.exists():
        return []

    try:
        data = json.loads(sample_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    cases: List[Dict[str, Any]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        cases.append(to_ui_queue_case(item, index=index))

    return cases

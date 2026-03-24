"""BE1/BE3와 합의된 엔티티 라벨 계약."""

from __future__ import annotations

from typing import Iterable, List, Set

ALLOWED_ENTITY_LABELS: Set[str] = {
    "LOCATION",
    "TIME",
    "FACILITY",
    "HAZARD",
    "ADMIN_UNIT",
}


def normalize_entity_label(value: str) -> str:
    return str(value).strip().upper()


def filter_allowed_entity_labels(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()

    for item in values:
        label = normalize_entity_label(item)
        if not label or label in seen or label not in ALLOWED_ENTITY_LABELS:
            continue
        seen.add(label)
        normalized.append(label)

    return normalized

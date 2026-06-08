"""B3/B4 — 긴급도 라벨 데이터셋 조인 (labels.jsonl + raw_data 본문)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.structuring.preprocessing import load_civil_index

LEVELS3 = ["낮음", "보통", "높음"]   # 긴급(희소 1건)은 높음에 흡수, 긴급 등급은 오버라이드/스코어가 산출


def fold_level3(level: str) -> str:
    return "높음" if level == "긴급" else level


def load_labeled_dataset(labels_path: str, processed_path: str) -> List[Dict[str, Any]]:
    """라벨 + **민원인 원문(title+client_question)** 조인.

    processed_path = data/processed/processed_consulting_data.json (상담사 답변 제외).
    → [{case_id, text, category, urgency_level, level3, safety_flag}].
    """
    idx = load_civil_index(processed_path)
    out: List[Dict[str, Any]] = []
    for line in Path(labels_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        cid = str(r["case_id"])
        src = idx.get(cid)
        if not src or not src["text"].strip():
            continue
        out.append({
            "case_id": cid,
            "text": src["text"],
            "category": src["category"],
            "urgency_level": r["urgency_level"],
            "level3": fold_level3(r["urgency_level"]),
            "safety_flag": int(r.get("safety_flag", 0)),
        })
    return out

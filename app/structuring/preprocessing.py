"""전처리 데이터(processed_consulting_data.json) → BE1 구조화 입력 어댑터.

원천 consulting_content = "제목 + Q(민원인) + A(상담사)".
구조화·긴급도는 **민원인 원문만** 대상으로 해야 하므로, 전처리로 분리된
title + client_question 만 사용하고 consultant_answer(상담사 답변)는 제외한다.

입력 레코드(전처리 산출) 주요 키:
  source_id, source, consulting_date, consulting_category,
  title, client_question, consultant_answer, ...
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def civil_text(rec: Dict[str, Any]) -> str:
    """민원인 원문 = title + client_question (상담사 답변 제외).

    title 을 포함하는 이유: Q 가 비었거나("…내용이 title 에"), Q 가 제목을
    참조("제목 내용처럼")하는 케이스에서 title 이 본문 신호를 보강한다.
    """
    title = str(rec.get("title") or "").strip()
    q = str(rec.get("client_question") or "").strip()
    if title and q:
        # Q 가 이미 title 로 시작하면 중복 방지
        return q if q.startswith(title) else f"{title}\n{q}"
    return (q or title).strip()


def to_structuring_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """전처리 레코드 → StructuringService.structure() 입력 dict."""
    return {
        "case_id": str(rec.get("source_id") or "").strip(),
        "text": civil_text(rec),                      # ← 민원인 원문(상담사 제외)
        "category": str(rec.get("consulting_category") or "미분류").strip() or "미분류",
        "region": str(rec.get("source") or "").strip(),
        "created_at": str(rec.get("consulting_date") or "").strip(),
        "source": str(rec.get("source") or "").strip(),
        "metadata": {
            "consulting_turns": rec.get("consulting_turns"),
            "original_length": rec.get("original_length"),
        },
    }


def load_processed(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def load_civil_index(path: str) -> Dict[str, Dict[str, str]]:
    """source_id → {text(민원인 원문), category} 인덱스 (긴급도 데이터셋 조인용)."""
    idx: Dict[str, Dict[str, str]] = {}
    for rec in load_processed(path):
        sid = str(rec.get("source_id") or "").strip()
        if sid:
            idx[sid] = {"text": civil_text(rec),
                        "category": str(rec.get("consulting_category") or "").strip()}
    return idx

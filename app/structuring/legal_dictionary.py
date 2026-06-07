"""법령 후보(legal_refs) 고도화 — Phase A.

기존 도메인 트리거 사전(enrichment.LEGAL_REF_LEXICON)에 더해,
법제처 현행법령 '목록'(법령명·약칭)과 부산 자치법규 목록을 사전으로 받아
민원 텍스트에 '직접 등장하는 법령명/약칭'을 매칭한다.

설계 의도:
  - 하드코딩 18개 → 현행법령 전체 + 부산 조례로 커버리지 확장.
  - 법령명/약칭 직접 매칭은 신뢰도가 높고(0.9~0.95) law_id 까지 부여 가능 →
    Phase B(조문 검색)에서 법령 필터로 바로 연결된다.
  - 사전 파일이 없으면 기존 도메인 lexicon 동작으로 안전 폴백(하위호환).

사전 파일은 scripts/build_law_dictionary.py 가 법제처 OPEN API(OC 키)로 생성한다.
이 모듈은 파일 I/O·매칭만 담당하며 네트워크를 호출하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.structuring.enrichment import classify_legal_refs

# 법령명/약칭 substring 매칭 최소 길이(오탐 방지).
_MIN_NAME_LEN = 3


def _norm_name(s: str) -> str:
    """가운뎃점 변형(·U+00B7 / ㆍU+318D / ‧U+2027)·공백 차이를 흡수."""
    return (s or "").replace("ㆍ", "").replace("·", "").replace("‧", "").replace(" ", "")

# 신뢰도(미보정 휴리스틱)
_CONF_NAME = 0.95      # 정식 법령명 직접 등장
_CONF_ABBR = 0.9       # 약칭 직접 등장
_CONF_ORDIN = 0.9      # 부산 자치법규명 직접 등장


def merge_legal_candidates(*lists: List[Dict[str, Any]], top_n: int = 4) -> List[Dict[str, Any]]:
    """여러 출처의 법령 후보를 name 기준으로 병합한다.

    같은 name 은 confidence 최댓값을 취하고 evidence/source/law_id 를 보존한다.
    confidence 내림차순, 상위 top_n.
    """
    by_name: Dict[str, Dict[str, Any]] = {}
    for lst in lists:
        for c in lst or []:
            name = str(c.get("name", "")).strip()
            if not name:
                continue
            cur = by_name.get(name)
            if cur is None or c.get("confidence", 0) > cur.get("confidence", 0):
                # 더 높은 신뢰도 후보로 교체하되 evidence 는 합친다
                merged_ev = list(dict.fromkeys(
                    (cur.get("evidence", []) if cur else []) + list(c.get("evidence", []))
                ))
                entry = dict(c)
                entry["evidence"] = merged_ev[:4]
                by_name[name] = entry
            else:
                cur_ev = cur.get("evidence", [])
                for e in c.get("evidence", []):
                    if e not in cur_ev:
                        cur_ev.append(e)
                cur["evidence"] = cur_ev[:4]
                # law_id/source 가 비어있으면 보강
                for k in ("law_id", "source"):
                    if not cur.get(k) and c.get(k):
                        cur[k] = c[k]
    out = sorted(by_name.values(), key=lambda r: r.get("confidence", 0), reverse=True)
    return out[:top_n]


class LegalRefMatcher:
    """사전 기반 법령명/약칭 매칭 + 도메인 lexicon 병합."""

    def __init__(
        self,
        dictionary_path: Optional[str] = None,
        ordinance_path: Optional[str] = None,
    ) -> None:
        from app.core.config import PROJECT_ROOT

        self.dictionary_path = Path(dictionary_path) if dictionary_path else (PROJECT_ROOT / "data" / "laws" / "law_dictionary.json")
        self.ordinance_path = Path(ordinance_path) if ordinance_path else (PROJECT_ROOT / "data" / "laws" / "busan_ordinances.json")
        self._loaded = False
        # [(name, meta)] — name 길이 내림차순(긴 이름 우선 매칭)
        self._law_names: List = []
        self._law_abbrs: List = []
        self._ordin_names: List = []
        self._name_to_law_id: Dict[str, str] = {}  # 정규화 법령명 → law_id (도메인 후보 보강용)

    # ── 사전 로딩 (선택) ─────────────────────────────────────────────────
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._law_names = self._index(self.dictionary_path, surface_key="name")
        self._law_abbrs = self._index(self.dictionary_path, surface_key="abbr")
        self._ordin_names = self._index(self.ordinance_path, surface_key="name")
        for surface, meta in self._law_names + self._ordin_names:
            lid = str(meta.get("law_id") or meta.get("id") or "").strip()
            if lid:
                self._name_to_law_id.setdefault(_norm_name(surface), lid)

    @staticmethod
    def _index(path: Path, surface_key: str) -> List:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        pairs = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            surface = str(item.get(surface_key) or "").strip()
            if len(surface) < _MIN_NAME_LEN:
                continue
            pairs.append((surface, item))
        # 긴 표면형 우선 (부분문자열 스킵용)
        pairs.sort(key=lambda p: len(p[0]), reverse=True)
        return pairs

    # ── 매칭 ─────────────────────────────────────────────────────────────
    def match(self, text: str, top_n: int = 4) -> List[Dict[str, Any]]:
        """민원 텍스트 → 법령 후보 (사전 직접매칭 + 도메인 lexicon 병합)."""
        self._load()
        text = text or ""

        name_hits = self._match_names(text, self._law_names, _CONF_NAME, "name_match")
        abbr_hits = self._match_names(text, self._law_abbrs, _CONF_ABBR, "abbr_match", formal_key="name")
        ordin_hits = self._match_names(text, self._ordin_names, _CONF_ORDIN, "ordinance")

        # 도메인 lexicon (법령명이 직접 안 적힌 민원 보강) — source 표시 + 사전에서 law_id 해석
        domain_hits = []
        for c in classify_legal_refs(text):
            c = dict(c)
            c["source"] = "domain"
            c["law_id"] = self._name_to_law_id.get(_norm_name(c.get("name", "")), "")
            domain_hits.append(c)

        return merge_legal_candidates(name_hits, abbr_hits, ordin_hits, domain_hits, top_n=top_n)

    @staticmethod
    def _match_names(
        text: str, pairs: List, confidence: float, source: str,
        formal_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        selected: List[str] = []
        for surface, meta in pairs:
            if surface not in text:
                continue
            # 이미 매칭된 더 긴 표면형의 부분문자열이면 건너뜀 (형법 vs 군형법)
            if any(surface != s and surface in s for s in selected):
                continue
            selected.append(surface)
            display = str(meta.get(formal_key) or surface).strip() if formal_key else surface
            hits.append({
                "name": display,
                "confidence": confidence,
                "evidence": [surface],
                "law_id": str(meta.get("law_id") or meta.get("id") or ""),
                "source": source,
            })
        return hits


_matcher: Optional[LegalRefMatcher] = None


def get_legal_ref_matcher() -> LegalRefMatcher:
    global _matcher
    if _matcher is None:
        _matcher = LegalRefMatcher()
    return _matcher

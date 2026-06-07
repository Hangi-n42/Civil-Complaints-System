"""법령 조문 코퍼스 — Phase B (조문 단위 본문).

법제처 lawService.do(본문) JSON 을 '조(條) 단위' 레코드로 파싱하고,
답변 초안의 조문 인용을 검색결과와 대조해 환각을 차단한다.

설계:
  - 검색 단위 = 조(article). law_id 를 메타로 박아 Phase A 후보(legal_refs.law_id)가
    그대로 조문 검색의 '법령 필터'가 되도록 한다.
  - 파서는 순수 함수(네트워크 없음) → 단위 테스트 가능. 본문 수집은
    scripts/build_law_corpus.py 가 담당.

응답 스키마 주의:
  법제처 lawService(target=law) 본문 JSON 은 루트 "법령"(자치법규는 "자치법규") 아래
  조문이 "조문"/"조문단위" 배열로 온다. 키 변형 대비 다중 후보로 방어적 파싱하며,
  최초 1회는 실제 응답으로 SAMPLE 을 확인할 것(빌더 주석 참조).
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional

# 본문 루트 키 후보(법령 / 자치법규)
_ROOT_KEYS = ["법령", "자치법규", "Law", "LawService"]
# 조문 '단위' 를 식별하는 마커 키(법령·자치법규 공통). 컨테이너 키 이름에 의존하지 않는다.
_ARTICLE_MARK_KEYS = ["조문번호", "조문내용", "조번호", "조내용"]
# 항(項) 단위에만 있는 키(조문 단위와 구분).
_HANG_ONLY_KEYS = ["항번호", "항내용"]
# 자치법규/법령 필드명 변형 후보
_NO_KEYS = ["조문번호", "조번호"]
_BRANCH_KEYS = ["조문가지번호", "조가지번호"]
_CONTENT_KEYS = ["조문내용", "조내용", "내용"]
_TITLE_KEYS = ["조문제목", "조제목"]


def _as_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v]
    return []


def _is_article_unit(d: Any) -> bool:
    if not isinstance(d, dict):
        return False
    if any(k in d for k in _HANG_ONLY_KEYS) and "조문번호" not in d:
        return False  # 항(項) 단위는 제외
    return any(k in d for k in _ARTICLE_MARK_KEYS)


def _find_article_units(node: Any) -> List[Dict[str, Any]]:
    """응답 트리 어디에 있든 '조문 단위 dict 들의 리스트'를 찾아 반환한다.

    컨테이너 키 이름(조문/조문단위/조 …)이 법령과 자치법규에서 다르더라도,
    조문 단위 마커(조문번호/조문내용)를 가진 dict 들의 '가장 큰 리스트'를 채택한다.
    """
    best: List[Dict[str, Any]] = []

    def walk(n: Any) -> None:
        nonlocal best
        if isinstance(n, list):
            units = [x for x in n if _is_article_unit(x)]
            if len(units) > len(best):
                best = units
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            for v in n.values():
                walk(v)

    walk(node)
    return best


def _get_first(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def _scalar(v: Any) -> Any:
    """값이 리스트면 첫 비어있지 않은 원소를 반환(자치법규 조문번호=리스트 대응)."""
    if isinstance(v, list):
        for x in v:
            if x not in (None, ""):
                return x
        return ""
    return v


def format_article_no(jo: str, ga: str = "") -> str:
    """조문번호(+가지번호) → '제3조' / '제3조의2'.

    법제처는 조문번호를 '000300'(6자리, 조2자리/항... )처럼 주기도 하고 '3'처럼 주기도 한다.
    숫자만 추출해 정규화한다.
    """
    jo_s = str(_scalar(jo) or "").strip()
    ga_s = str(_scalar(ga) or "").strip()
    # 6자리 코드면 앞 4자리가 조, 뒤 2자리가 가지인 관례 → 우선 숫자화
    if jo_s.isdigit() and len(jo_s) >= 5:
        num = int(jo_s[:-2]) if len(jo_s) > 2 else int(jo_s)
        branch = int(jo_s[-2:])
        base = f"제{num}조"
        return f"{base}의{branch}" if branch else base
    m = re.search(r"\d+", jo_s)
    if not m:
        return jo_s or "제0조"
    base = f"제{int(m.group())}조"
    gm = re.search(r"\d+", ga_s)
    if gm and int(gm.group()) > 0:
        return f"{base}의{int(gm.group())}"
    return base


def _article_text(unit: Dict[str, Any]) -> str:
    """조문내용 우선, 비면 항/호 내용을 조립."""
    content = str(_get_first(unit, _CONTENT_KEYS, "") or "").strip()
    if content:
        return content
    parts: List[str] = []
    title = str(_get_first(unit, _TITLE_KEYS, "") or "").strip()
    no = str(_get_first(unit, _NO_KEYS, "") or "").strip()
    if no:
        parts.append(f"제{re.sub(r'[^0-9]', '', no) or no}조" + (f"({title})" if title else ""))
    for hang in _as_list(_get_first(unit, ["항"], [])):
        if isinstance(hang, dict):
            ht = str(_get_first(hang, ["항내용", "내용"], "") or "").strip()
            if ht:
                parts.append(ht)
    return "\n".join(parts).strip()


def parse_law_body(
    meta: Dict[str, Any],
    body: Dict[str, Any],
    source_url: str = "",
) -> List[Dict[str, Any]]:
    """lawService 본문 JSON → 조 단위 레코드 리스트.

    meta: {law_id, name, type, dept, enforce_date, doc_type}  (Phase A 사전 항목 + doc_type)
    body: lawService.do 응답(JSON dict)
    """
    root = None
    for k in _ROOT_KEYS:
        if isinstance(body.get(k), dict):
            root = body[k]
            break
    if root is None:
        root = body  # 루트가 평면일 수도 있음

    units = _find_article_units(root)

    law_id = str(meta.get("law_id") or "").strip()
    law_name = str(meta.get("name") or meta.get("law_name") or "").strip()
    doc_type = str(meta.get("doc_type") or "law").strip()
    enforce_date = str(meta.get("enforce_date") or "").strip()
    dept = str(meta.get("dept") or "").strip()

    records: List[Dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        # 조문여부: '조문'만 채택(전문/편/장/절 제목 제외). 키 없으면 내용 유무로 판단.
        # 조문여부: 법령="조문", 자치법규="Y". 그 외(전문/편/장/절 등)는 제외.
        yn = str(_get_first(unit, ["조문여부"], "") or "")
        if yn and yn not in ("조문", "Y"):
            continue
        text = _article_text(unit)
        if not text:
            continue
        article_no = format_article_no(
            _get_first(unit, _NO_KEYS, ""),
            _get_first(unit, _BRANCH_KEYS, ""),
        )
        records.append({
            "doc_id": f"{doc_type}:{law_id}:{article_no}",
            "law_id": law_id,
            "law_name": law_name,
            "doc_type": doc_type,
            "article_no": article_no,
            "article_title": str(_get_first(unit, _TITLE_KEYS, "") or "").strip(),
            "text": text,
            "enforce_date": enforce_date,
            "dept": dept,
            "source_url": source_url,
        })
    return records


# ──────────────────────────────────────────────────────────────────────────
# 인용 환각 방지 — 답변 초안의 (법령명, 조문번호)를 검색결과와 대조
# ──────────────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip()


def _norm_article_no(s: str) -> str:
    """'제3조의2' / '3조의2' / '제 3 조' → '제3조의2' 표준화."""
    s = _norm(s)
    m = re.search(r"제?(\d+)조(?:의(\d+))?", s)
    if not m:
        return s
    base = f"제{int(m.group(1))}조"
    return f"{base}의{int(m.group(2))}" if m.group(2) else base


def public_law_url(law_name: str, article_no: str = "", doc_type: str = "law") -> str:
    """사용자 노출용 공개 URL(국가법령정보센터). OC 키가 든 DRF source_url 대체."""
    seg = "자치법규" if doc_type == "ordinance" else "법령"
    name = urllib.parse.quote((law_name or "").strip())
    url = f"https://www.law.go.kr/{seg}/{name}"
    if article_no:
        url += f"/{urllib.parse.quote(str(article_no).strip())}"
    return url


def validate_citations(
    citations: List[Dict[str, Any]],
    retrieved: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """답변 초안 인용을 검색된 조문 집합과 대조한다.

    Args:
        citations: LLM 이 생성한 [{"law_name", "article_no", ...}, ...]
        retrieved: 답변 컨텍스트로 제공된 조문 레코드(parse_law_body 산출)

    Returns:
        {"valid": [...], "invalid": [...]}  invalid = 검색결과에 없는(환각 가능) 인용
        valid 항목에는 매칭된 source_url/law_id 를 부여한다.
    """
    allowed: Dict[tuple, Dict[str, Any]] = {}
    for r in retrieved or []:
        key = (_norm(r.get("law_name")), _norm_article_no(r.get("article_no")))
        allowed[key] = r

    valid, invalid = [], []
    for c in citations or []:
        key = (_norm(c.get("law_name")), _norm_article_no(c.get("article_no")))
        match = allowed.get(key)
        if match:
            out = dict(c)
            out["law_id"] = match.get("law_id", "")
            out["source_url"] = match.get("source_url", "")
            out["doc_type"] = match.get("doc_type", "law")
            out["verified"] = True
            valid.append(out)
        else:
            out = dict(c)
            out["verified"] = False
            invalid.append(out)
    return {"valid": valid, "invalid": invalid}

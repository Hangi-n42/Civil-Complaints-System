"""BE3 법령 조문 인용 그라운딩 + 환각 검증 — Phase B 연동.

흐름:
  1) retrieve_legal_context(): BE1 legal_refs(law_id)가 있을 때만 조문 검색(Phase A→B).
  2) build_legal_context_block() + LEGAL_CITATION_INSTRUCTION: 프롬프트에 [법령 조문] 주입.
  3) (BE3가 LLM 생성)
  4) ground_legal_citations(): 답변에서 (법령명, 조문번호) 인용을 추출해 검색 조문과 대조.
     검증 실패(환각) 인용은 답변에서 '제거 + 경고 플래그'.

순수 함수(extract/build/strip/ground)는 모델 없이 테스트 가능.
조문 검색은 app.retrieval.law_article_store 재사용(Dense 미가용 시 BM25 폴백).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.structuring.law_corpus import public_law_url, validate_citations

# "제80조" / "제80조의2" (공백 허용)
_ARTICLE_RE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
# prefix 꼬리에서 법령명(…법/법률/시행령/시행규칙/규칙/조례/규정) 포착
_LAWNAME_TAIL = re.compile(
    r"([가-힣A-Za-z0-9()ㆍ·]+(?:\s[가-힣A-Za-z0-9()ㆍ·]+){0,6}?"
    r"(?:법률|시행령|시행규칙|법|규칙|조례|규정))\s*$"
)
_PREFIX_WINDOW = 50

CITATION_REMOVED_MARKER = "[미검증 인용 제거]"

LEGAL_CITATION_INSTRUCTION = (
    "법령 조문을 인용할 때는 아래 [법령 조문]에 제시된 (법령명, 조문번호)만 사용하세요. "
    "목록에 없는 조문 번호를 만들지 마세요. 인용 형식은 '○○법 제□조'로 쓰세요."
)


def extract_legal_citations(
    text: str,
    known_law_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """답변 텍스트에서 (법령명, 조문번호) 인용을 추출한다.

    known_law_names(검색된 조문의 법령명)가 주어지면 prefix 에서 우선 매칭(정밀도↑).
    각 항목: {law_name, article_no, raw, _span:(start,end)}  (_span = 제거용 범위)
    """
    text = text or ""
    known = sorted({n for n in (known_law_names or []) if n}, key=len, reverse=True)
    out: List[Dict[str, Any]] = []
    for m in _ARTICLE_RE.finditer(text):
        jo = int(m.group(1))
        article_no = f"제{jo}조" + (f"의{int(m.group(2))}" if m.group(2) else "")
        ps = max(0, m.start() - _PREFIX_WINDOW)
        prefix = text[ps:m.start()]

        law_name = ""
        law_start = m.start()
        for kn in known:                       # 1) 검색된 법령명 우선
            idx = prefix.rfind(kn)
            if idx != -1:
                law_name = kn
                law_start = ps + idx
                break
        if not law_name:                       # 2) 일반 법령명 꼬리 포착
            tm = _LAWNAME_TAIL.search(prefix)
            if tm:
                law_name = tm.group(1).strip()
                law_start = ps + tm.start(1)

        out.append({
            "law_name": law_name,
            "article_no": article_no,
            "raw": text[law_start:m.end()].strip(),
            "_span": (law_start, m.end()),
        })
    return out


def build_legal_context_block(articles: List[Dict[str, Any]], max_articles: int = 5,
                              max_chars: int = 280) -> str:
    """검색된 조문을 프롬프트용 [법령 조문] 블록으로 직렬화."""
    lines = ["[법령 조문]"]
    for a in articles[:max_articles]:
        text = " ".join(str(a.get("text", "")).split())[:max_chars]
        lines.append(f"- {a.get('law_name','')} {a.get('article_no','')}: {text}")
    return "\n".join(lines)


def _strip_spans(text: str, spans: List[tuple]) -> str:
    """span 들을 마커로 치환(뒤에서부터 처리해 인덱스 보존)."""
    for start, end in sorted(spans, key=lambda s: s[0], reverse=True):
        text = text[:start] + CITATION_REMOVED_MARKER + text[end:]
    return text


def ground_legal_citations(
    answer_text: str,
    retrieved_articles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """답변의 법령 인용을 검색 조문과 대조 → 환각 인용 제거 + 플래그.

    Returns:
        {
          "answer": 검증 후 답변(환각 인용 제거),
          "valid": [...검증된 인용(+public_url/law_id, source_url 제외)...],
          "invalid": [...환각 인용...],
          "warnings": ["미검증 인용 제거: ..."],
        }
    """
    known = [a.get("law_name", "") for a in retrieved_articles]
    cites = extract_legal_citations(answer_text, known_law_names=known)
    res = validate_citations(cites, retrieved_articles)

    invalid_spans = [c["_span"] for c in res["invalid"] if c.get("_span")]
    cleaned = _strip_spans(answer_text, invalid_spans)
    warnings = [f"미검증 인용 제거: {c.get('raw') or c.get('law_name','')+' '+c.get('article_no','')}"
                for c in res["invalid"]]

    def _clean(items: List[Dict[str, Any]], add_public: bool = False) -> List[Dict[str, Any]]:
        result = []
        for c in items:
            c = {
                k: v
                for k, v in c.items()
                if k not in {"_span", "source_url"}
            }
            if add_public:
                c["public_url"] = public_law_url(
                    c.get("law_name", ""), c.get("article_no", ""), c.get("doc_type", "law"))
            result.append(c)
        return result

    return {
        "answer": cleaned,
        "valid": _clean(res["valid"], add_public=True),
        "invalid": _clean(res["invalid"]),
        "warnings": warnings,
    }


def retrieve_legal_context(
    query: str,
    legal_refs: List[Dict[str, Any]],
    key_terms: Optional[List[str]] = None,
    top_k: int = 5,
    store: Any = None,
) -> List[Dict[str, Any]]:
    """legal_refs(law_id)가 있을 때만 조문을 검색해 반환. 없으면 [] (그라운딩 생략)."""
    law_ids = [str(r.get("law_id")) for r in (legal_refs or []) if r.get("law_id")]
    if not law_ids:
        return []
    if store is None:
        from app.retrieval.law_article_store import get_law_article_store
        store = get_law_article_store()
    return store.search(query, law_ids=law_ids, key_terms=key_terms, top_k=top_k)

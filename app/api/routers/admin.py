"""관리자 통계 API — 카테고리별 발생 현황(부서 라우팅 기반 부산 대분류) 집계.

civil_cases_v3는 2009~2024 정적 아카이브라 '지난 N일' 개념이 무의미하다.
그래서 연도(또는 전체) 단위로 civil_category.primary 분포를 집계해 반환한다.
v3 메타데이터에 civil_category가 아직 없으므로(재색인 전), responsible_units에서
adapter와 동일하게 classify_civil_category로 즉석 계산한다.
데이터가 정적이므로 인덱스는 1회 계산 후 메모리에 캐시한다.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.api.error_utils import error_response, make_request_id, now_iso
from app.core.config import settings
from app.core.logging import api_logger
from app.structuring.civil_category import classify_civil_category

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_UNCLASSIFIED = "미분류"
# (primary, year) 인덱스 캐시 — 정적 아카이브라 한 번만 계산한다.
_doc_index: Optional[List[Dict[str, Optional[str]]]] = None


def _split_pipe(value: Any) -> List[str]:
    """Chroma 메타의 파이프 조인 문자열('A|B|C')을 리스트로 되돌린다."""
    if not value:
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def aggregate_categories(index: List[Dict[str, Optional[str]]], year: Optional[str]) -> Dict[str, Any]:
    """(primary, year) 인덱스 → 연도 필터 + primary별 건수 집계 (순수 함수, 테스트 대상)."""
    available_years = sorted({d["year"] for d in index if d.get("year")}, reverse=True)
    selected = year if (year and year != "all") else None
    rows = [d for d in index if selected is None or d.get("year") == selected]
    counts = Counter(d.get("primary") or _UNCLASSIFIED for d in rows)
    categories = [{"name": name, "count": count} for name, count in counts.most_common()]
    return {
        "year": selected or "all",
        "available_years": available_years,
        "total": len(rows),
        "categories": categories,
    }


def _count_values(rows: List[Dict[str, Any]], getter) -> Counter:
    """스칼라 또는 리스트 필드를 건수로 집계한다(리스트는 항목별 가산)."""
    counts: Counter = Counter()
    for row in rows:
        value = getter(row)
        if isinstance(value, list):
            for item in value:
                if item:
                    counts[item] += 1
        elif value:
            counts[value] += 1
    return counts


def aggregate_overview(
    index: List[Dict[str, Any]],
    year: Optional[str],
    categories: Optional[List[str]] = None,
    top_n: int = 8,
) -> Dict[str, Any]:
    """대시보드 전체 실데이터 집계: 카테고리/지역/이슈유형 + 연도별 추이.

    year: 연도 필터(지역·이슈·건수에 적용). categories: 카테고리 드릴다운(복수 선택,
    합집합). 선택된 분야 중 하나라도 해당하면 포함하며 지역·이슈·건수·추이에 적용한다.
    카테고리 목록(반환 'categories')은 셀렉터이므로 연도만 반영한다.
    """
    base = aggregate_categories(index, year)  # 반환 categories는 셀렉터(연도만 반영)
    selected_year = year if (year and year != "all") else None
    if isinstance(categories, str):  # 단일 문자열로 와도 허용
        categories = [categories]
    selected_cats = {c for c in categories if c} if categories else None

    def _match(d: Dict[str, Any]) -> bool:
        if selected_year is not None and d.get("year") != selected_year:
            return False
        if selected_cats is not None and (d.get("primary") or _UNCLASSIFIED) not in selected_cats:
            return False
        return True

    rows = [d for d in index if _match(d)]
    regions = _count_values(rows, lambda d: d.get("region"))
    issues = _count_values(rows, lambda d: d.get("issues"))

    # 연도별 추이는 연도 축이라 연도 필터는 안 받지만, 카테고리 드릴다운은 반영한다.
    trend_rows = [
        d for d in index
        if selected_cats is None or (d.get("primary") or _UNCLASSIFIED) in selected_cats
    ]
    year_counts = Counter(d["year"] for d in trend_rows if d.get("year"))
    trend = [{"year": y, "count": year_counts[y]} for y in sorted(year_counts)]

    return {
        **base,
        "category": sorted(selected_cats) if selected_cats else [],
        "total": len(rows),  # 연도만 반영한 base.total을 카테고리까지 반영한 값으로 덮어쓴다
        "regions": [{"name": name, "count": count} for name, count in regions.most_common(top_n)],
        "issues": [{"name": name, "count": count} for name, count in issues.most_common(top_n)],
        "trend": trend,
    }


def _primary_for(meta: Dict[str, Any]) -> str:
    """단일 케이스 메타데이터에서 civil_category.primary를 계산한다(adapter와 동일 신호)."""
    depts = _split_pipe(meta.get("responsible_units"))
    responsible_unit = [{"name": d} for d in depts] or None
    text = " ".join(
        part
        for part in (
            str(meta.get("summary_observation") or ""),
            str(meta.get("summary_request") or ""),
            str(meta.get("title") or ""),
        )
        if part
    )
    civil = classify_civil_category(
        text=text,
        category=meta.get("category") or "",
        responsible_unit=responsible_unit,
        entity_texts=_split_pipe(meta.get("entity_texts")),
        key_terms=_split_pipe(meta.get("key_terms")),
    )
    return (civil or {}).get("primary") or _UNCLASSIFIED


def _build_index() -> List[Dict[str, Optional[str]]]:
    global _doc_index
    if _doc_index is not None:
        return _doc_index

    import chromadb

    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    collection = client.get_collection(settings.DEFAULT_CHROMA_COLLECTION)
    result = collection.get(include=["metadatas"])

    seen: set = set()
    index: List[Dict[str, Optional[str]]] = []
    for meta in result.get("metadatas") or []:
        case_id = str(meta.get("case_id") or meta.get("doc_id") or "")
        if case_id and case_id in seen:
            continue
        if case_id:
            seen.add(case_id)
        created = str(meta.get("created_at") or "")
        year = created[:4] if created[:4].isdigit() else None
        index.append({
            "primary": _primary_for(meta),
            "year": year,
            "region": (str(meta.get("region") or "").strip() or None),
            "issues": _split_pipe(meta.get("issue_types")),
        })

    _doc_index = index
    return index


@router.get("/overview")
async def overview(
    year: Optional[str] = None,
    category: Optional[List[str]] = Query(default=None),
):
    """관리자 대시보드 실데이터 종합: 카테고리/지역/이슈유형/연도별 추이.

    year=연도(예 '2024') 또는 'all'(기본). category=카테고리 드릴다운(복수 가능,
    예 '?category=사회복지&category=교통·물류'). 카테고리 목록은 셀렉터라 연도만
    반영하고, 지역·이슈·건수·추이는 선택된 분야 합집합으로 반영한다.
    """
    request_id = make_request_id()
    try:
        index = _build_index()
    except Exception as exc:  # 인덱스/컬렉션 미가용
        api_logger.error(
            "api_error endpoint=%s request_id=%s error_code=%s message=%s",
            "/api/v1/admin/overview",
            request_id,
            "INTERNAL_SERVER_ERROR",
            str(exc),
        )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="대시보드 통계 집계 중 오류가 발생했습니다.",
            retryable=True,
            details={"reason": str(exc)},
        )

    return {
        "success": True,
        "request_id": request_id,
        "timestamp": now_iso(),
        "data": aggregate_overview(index, year, category),
    }

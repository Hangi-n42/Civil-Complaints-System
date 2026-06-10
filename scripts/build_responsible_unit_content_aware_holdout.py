"""responsible_unit holdout1000 자동 라벨을 content-aware 방식으로 재정제한다.

이 스크립트는 평가셋 gold 품질 개선용이며 운영 추론 로직에 사용하지 않는다.
모델 예측 결과는 입력으로 받지 않고, query 본문 + consulting_category +
busan_departments_master.json의 실제 부서명만 사용한다.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "departments" / "eval" / "responsible_unit_holdout1000.auto.jsonl"
DEFAULT_MASTER = ROOT / "data" / "departments" / "busan_departments_master.json"
DEFAULT_OUTPUT = ROOT / "data" / "departments" / "eval" / "responsible_unit_holdout1000.content_aware.jsonl"
DEFAULT_REVIEW = ROOT / "data" / "departments" / "eval" / "responsible_unit_holdout1000.content_aware.review.jsonl"
DEFAULT_REPORT = ROOT / "reports" / "responsible_unit_holdout1000_content_aware_labeling_report.md"

NONE_LABEL = "NONE"


def normalize(text: Any) -> str:
    """규칙 매칭을 위해 공백과 대소문자 차이를 줄인다."""
    return re.sub(r"\s+", "", str(text or "").casefold())


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """JSONL 파일을 읽는다."""
    rows: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no} 객체가 아닙니다.")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """JSONL 파일을 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def load_department_names(path: Path) -> set[str]:
    """마스터에서 배정 가능한 부서명을 읽는다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"마스터 파일 형식이 배열이 아닙니다: {path}")
    return {str(row.get("department", "")).strip() for row in data if row.get("department")}


def any_term(text: str, terms: Sequence[str]) -> List[str]:
    """본문에 들어있는 단일 키워드를 evidence로 반환한다."""
    found: List[str] = []
    for term in terms:
        if normalize(term) in text and term not in found:
            found.append(term)
    return found


def any_group(text: str, groups: Sequence[Sequence[str]]) -> List[str]:
    """AND 키워드 그룹 중 본문에 모두 들어있는 항목을 evidence로 반환한다."""
    found: List[str] = []
    for group in groups:
        if all(normalize(term) in text for term in group):
            label = " ".join(group)
            if label not in found:
                found.append(label)
    return found


def merge_evidence(*items: Iterable[str], limit: int = 8) -> List[str]:
    """근거 단어를 중복 없이 합친다."""
    out: List[str] = []
    for values in items:
        for value in values:
            text = str(value or "").strip()
            if text and text not in out:
                out.append(text)
            if len(out) >= limit:
                return out
    return out


def make_labeled_row(
    row: Dict[str, Any],
    *,
    gold: Sequence[str],
    confidence: str,
    evidence: Sequence[str],
    note: str,
    source: str = "content_aware_alias",
) -> Dict[str, Any]:
    """새 라벨 row를 만든다."""
    return {
        "id": row.get("id", ""),
        "case_id": row.get("case_id", ""),
        "source_id": row.get("source_id", ""),
        "query": row.get("query", ""),
        "original_consulting_category": row.get("consulting_category", ""),
        "old_gold": row.get("gold", []),
        "gold": list(gold),
        "label_source": source,
        "label_confidence": confidence,
        "label_evidence": list(evidence),
        "label_note": note,
    }


def make_review_row(
    row: Dict[str, Any],
    *,
    confidence: str,
    evidence: Sequence[str],
    note: str,
    suggested_gold: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """사람 검수가 필요한 row를 만든다."""
    return {
        "id": row.get("id", ""),
        "case_id": row.get("case_id", ""),
        "source_id": row.get("source_id", ""),
        "query": row.get("query", ""),
        "original_consulting_category": row.get("consulting_category", ""),
        "old_gold": row.get("gold", []),
        "suggested_gold": list(suggested_gold or []),
        "label_source": "content_aware_review",
        "label_confidence": confidence,
        "label_evidence": list(evidence),
        "label_note": note,
    }


def decide_content_aware_label(row: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """단일 holdout row의 content-aware 라벨을 결정한다.

    반환값 첫 번째 요소는 "main" 또는 "review"다.
    """
    category = str(row.get("consulting_category") or "").strip()
    old_gold = [str(x).strip() for x in row.get("gold", []) if str(x).strip()]
    query = str(row.get("query") or "")
    text = normalize(query)

    # 제도/시설별 본문 근거 사전. 단일 강한 제도명 또는 2개 이상의 약한 단서일 때 확정한다.
    road_terms = any_term(text, ("도로", "보도", "인도", "통행", "보행", "맨홀", "가로등", "보안등", "포트홀", "도로파손", "균열", "도로관리", "교통사고", "위험", "볼트"))
    sewer_terms = any_term(text, ("하수", "하수관", "하수도", "배수", "배수구", "악취", "오수", "토구", "분뇨"))
    construction_admin_terms = any_term(text, ("전문건설업", "종합건설업", "건설업등록", "건설기술자", "기계설비법", "기계설비유지관리자", "표준시장단가", "하도급", "건설산업기본법", "기재사항변경"))
    building_terms = any_term(text, ("건축법", "건축물", "건축허가", "용도변경", "방화창", "방화유리창", "방화구획", "방화댐퍼", "내진설계", "조경면적", "창호", "열관류율", "위반건축물", "건축물대장", "주차장법", "부설주차장", "주차대수"))
    housing_terms = any_term(text, ("공동주택", "아파트", "민간임대주택", "임대사업자", "주택임대사업자", "표준임대차", "렌트홈", "장기수선충당금", "입주자대표회의", "관리규약", "주택건설기준", "청약"))
    urban_plan_terms = any_term(text, ("도시계획", "도시관리계획", "도시기본계획", "지구단위계획", "국토의계획및이용", "국토의 계획 및 이용", "국계법", "개발행위허가", "개발제한구역", "토지형질변경", "토지거래허가구역", "용도지역", "용도지구", "건폐율", "용적률"))
    facility_plan_terms = any_term(text, ("도시계획시설사업", "실시계획인가", "시설결정", "지형도면고시", "사업시행자지정", "도시계획시설"))
    urban_vitality_terms = any_term(text, ("도시재생", "노후계획도시", "도시재생사업", "도시재생전략계획"))
    forest_terms = any_term(text, ("산지", "산림", "보전산지", "산지전용", "숲길", "등산로", "임야", "도시숲", "나무병원", "토석채취", "금정산"))
    park_terms = any_term(text, ("공원", "어린이공원", "근린공원", "도시공원", "공원시설", "황톳길", "맨발걷기", "물놀이장", "놀이터", "공원관리"))
    strong_park_terms = [term for term in park_terms if term != "공원"]
    bus_terms = any_term(text, ("버스", "버스노선", "버스정류장", "정류장", "배차", "증차", "시내버스", "마을버스", "광역버스", "난폭운전"))
    rail_terms = any_term(text, ("철도", "지하철", "전철", "도시철도", "역출구", "출구", "정거장", "역세권", "철도노선", "철도건설", "서해선", "7호선"))
    startup_terms = any_term(text, ("창업", "스타트업", "벤처", "창업지원", "창업비용", "창업자", "법인설립", "주금납입", "잔고증명"))
    small_business_terms = any_term(text, ("소상공인", "자영업", "상가", "상권", "지역사랑상품권", "상품권", "사업자등록", "소상공인대출", "신용보증"))
    jobs_terms = any_term(text, ("고용", "일자리", "4대보험", "직업능력", "훈련시설", "근로자", "고용장려금", "특고"))
    enterprise_terms = any_term(text, ("기업", "제조업", "산업단지", "지식산업센터", "시설투자", "공장", "업종분류"))
    tourism_terms = any_term(text, ("관광", "여행", "해수욕장", "캠핑", "관광지", "가이드", "패키지"))
    culture_terms = any_term(text, ("문화", "예술", "공연", "축제", "문화시설", "예술영재"))
    environment_terms = any_term(text, ("소음", "비산먼지", "대기", "악취", "빛공해", "환경오염", "흡연"))
    energy_terms = any_term(text, ("태양광", "신재생에너지", "발전", "에너지", "수소", "전기요금"))
    childcare_terms = any_term(text, ("어린이집", "보육", "영유아", "보조교사", "국공립"))
    family_terms = any_term(text, ("아이돌봄", "가족", "다문화", "양성평등", "여성", "돌봄"))

    if category == "건설과":
        if len(sewer_terms) >= 2:
            return "main", make_labeled_row(row, gold=["공공하수인프라과"], confidence="high", evidence=sewer_terms, note="건설과 광역 카테고리이나 본문 핵심 객체가 하수/배수 기반시설임")
        if len(road_terms) >= 2:
            return "main", make_labeled_row(row, gold=["도로안전과"], confidence="high", evidence=road_terms, note="건설과 광역 카테고리이나 본문 핵심 객체가 도로/보행 안전 및 도로시설물 관리임")
        if construction_admin_terms:
            return "main", make_labeled_row(row, gold=["건설행정과"], confidence="high", evidence=construction_admin_terms, note="본문에 건설업 행정/기계설비 제도명이 명확함")
        if len(building_terms) >= 2:
            return "main", make_labeled_row(row, gold=["건축정책과"], confidence="medium", evidence=building_terms, note="건설과 광역 카테고리이나 본문은 건축 인허가/건축물 제도 문맥임")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(road_terms, sewer_terms, building_terms), note="건설과는 광역 카테고리라 본문만으로 부산시 본청 부서 확정이 어려움")

    if category in {"건설정책과", "건설산업과"}:
        if construction_admin_terms:
            return "main", make_labeled_row(row, gold=["건설행정과"], confidence="high", evidence=construction_admin_terms, note="건설정책/건설산업 카테고리와 건설업 행정 제도명이 함께 확인됨")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(road_terms, building_terms), note="건설정책/건설산업 카테고리이나 건설행정 업무 근거가 부족함")

    if category == "도시활력지원과":
        if urban_vitality_terms:
            return "main", make_labeled_row(row, gold=["도시공간활력과"], confidence="high", evidence=urban_vitality_terms, note="마스터상 도시공간활력과의 노후계획도시/도시재생 업무와 일치")
        if facility_plan_terms and len(facility_plan_terms) >= 2:
            return "main", make_labeled_row(row, gold=["시설계획과"], confidence="medium", evidence=facility_plan_terms, note="본문 핵심이 도시계획시설 실시계획/시설결정 업무임")
        if urban_plan_terms:
            return "main", make_labeled_row(row, gold=["도시계획과"], confidence="high", evidence=urban_plan_terms, note="도시활력지원과 alias 대신 본문상 도시계획/국계법 업무로 재분류")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(urban_plan_terms, facility_plan_terms), note="도시활력지원과는 부산시 마스터와 1:1 대응이 어려움")

    if category in {"녹색도시과", "녹지과"}:
        if forest_terms:
            return "main", make_labeled_row(row, gold=["푸른숲도시과"], confidence="high", evidence=forest_terms, note="본문 핵심이 산림/산지/숲길 업무임")
        if strong_park_terms:
            return "main", make_labeled_row(row, gold=["공원여가정책과"], confidence="medium", evidence=park_terms, note="녹지 계열 카테고리이나 본문 핵심 객체가 공원 시설/관리임")
        if urban_plan_terms:
            return "main", make_labeled_row(row, gold=["도시계획과"], confidence="medium", evidence=urban_plan_terms, note="녹색도시 계열이나 본문은 개발제한구역/도시계획 제도 문맥임")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(forest_terms, park_terms, urban_plan_terms), note="녹색/녹지 카테고리이나 산림·공원·도시계획 중 어느 축인지 불명확함")

    if category in {"공원과", "공원관리과", "녹지공원과"}:
        if park_terms:
            return "main", make_labeled_row(row, gold=["공원여가정책과"], confidence="high", evidence=park_terms, note="본문 핵심 객체가 공원 시설/공원 관리임")
        if forest_terms:
            return "main", make_labeled_row(row, gold=["푸른숲도시과"], confidence="medium", evidence=forest_terms, note="공원 계열 카테고리이나 본문은 산림/숲길 업무에 가까움")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(park_terms, forest_terms), note="공원 계열 카테고리이나 본문 근거가 부족함")

    if category == "생활교통복지과":
        if bus_terms:
            return "main", make_labeled_row(row, gold=["대중교통과"], confidence="high", evidence=bus_terms, note="생활교통복지과 중 버스/대중교통 본문 근거가 명확함")
        if building_terms and ("주차장법" in building_terms or "부설주차장" in building_terms or "주차대수" in building_terms):
            gold = ["건축정책과", "주택정책과"] if housing_terms else ["건축정책과"]
            return "main", make_labeled_row(row, gold=gold, confidence="medium", evidence=merge_evidence(building_terms, housing_terms), note="주차장 법령이 건축물/용도변경 또는 공동주택 문맥으로 제시됨")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(bus_terms, building_terms), note="생활교통복지과이나 대중교통/건축 주차장 중 명확한 축이 부족함")

    if category == "생태하천과":
        sewer_infra_terms = [term for term in sewer_terms if term != "악취"]
        if sewer_infra_terms:
            return "main", make_labeled_row(row, gold=["공공하수인프라과"], confidence="medium", evidence=sewer_terms, note="생태하천 카테고리이나 본문은 하수/배수 기반시설 문맥임")
        river_terms = any_term(text, ("하천", "강", "천", "범람", "제방", "둔치", "하천수질", "국가하천", "지방하천"))
        if river_terms:
            return "main", make_labeled_row(row, gold=["하천관리과"], confidence="high", evidence=river_terms, note="본문 핵심 객체가 하천 관리/치수 업무임")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(sewer_terms), note="생태하천 카테고리이나 하천/하수 구분 근거가 부족함")

    if category == "철도교통과":
        if rail_terms:
            return "main", make_labeled_row(row, gold=["철도시설과"], confidence="high", evidence=rail_terms, note="본문 핵심 객체가 철도/도시철도 시설임")
        if bus_terms:
            return "main", make_labeled_row(row, gold=["대중교통과"], confidence="medium", evidence=bus_terms, note="철도교통 카테고리이나 본문은 버스/대중교통 문맥임")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(rail_terms, bus_terms), note="철도교통 카테고리이나 철도/버스 본문 근거가 부족함")

    if category == "건축과":
        if building_terms:
            return "main", make_labeled_row(row, gold=["건축정책과"], confidence="high", evidence=building_terms, note="건축과 카테고리와 건축 제도/건축물 본문 근거가 일치")
        if len(road_terms) >= 2:
            return "main", make_labeled_row(row, gold=["도로안전과"], confidence="medium", evidence=road_terms, note="건축과 카테고리이나 본문 핵심이 도로/보행 안전임")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(building_terms, road_terms), note="건축과 카테고리이나 건축정책 근거가 부족함")

    if category == "창업":
        if startup_terms:
            return "main", make_labeled_row(row, gold=["창업벤처담당관"], confidence="high", evidence=startup_terms, note="본문 핵심이 창업/스타트업 지원임")
        if small_business_terms:
            return "main", make_labeled_row(row, gold=["중소상공인지원과"], confidence="medium", evidence=small_business_terms, note="창업 카테고리이나 본문은 소상공인/상권/신용보증 지원 문맥임")
        if jobs_terms:
            return "main", make_labeled_row(row, gold=["일자리노동과"], confidence="medium", evidence=jobs_terms, note="창업 카테고리이나 본문은 고용/직업훈련 문맥임")
        if enterprise_terms:
            return "main", make_labeled_row(row, gold=["기업지원과"], confidence="medium", evidence=enterprise_terms, note="창업 카테고리이나 본문은 기업/제조업 지원 문맥임")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(startup_terms, small_business_terms, jobs_terms, enterprise_terms), note="창업 카테고리이나 창업/소상공인/고용/기업지원 중 확정 근거가 부족함")

    if category == "문화관광과":
        if tourism_terms:
            return "main", make_labeled_row(row, gold=["관광정책과"], confidence="high", evidence=tourism_terms, note="문화관광과 중 관광/여행 본문 근거가 명확함")
        if culture_terms:
            return "main", make_labeled_row(row, gold=["문화예술과"], confidence="medium", evidence=culture_terms, note="문화관광과 중 문화예술 본문 근거가 명확함")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(tourism_terms, culture_terms), note="문화관광과이나 문화/관광 축이 불명확함")

    if category in {"도로과", "도로관리과", "구조물관리과", "시설안전과"}:
        if len(road_terms) >= 2:
            return "main", make_labeled_row(row, gold=["도로안전과"], confidence="high", evidence=road_terms, note="본문 핵심이 도로시설물/보행 안전 업무임")
        return "review", make_review_row(row, confidence="needs_review", evidence=road_terms, note="도로/시설 카테고리이나 도로안전 업무 근거가 부족함")

    if category in {"기후환경본부 대기정책과", "환경자원과"}:
        if environment_terms:
            return "main", make_labeled_row(row, gold=["환경정책과"], confidence="medium", evidence=environment_terms, note="환경 계열 카테고리와 환경오염/소음/대기 본문 근거가 일치")
        if energy_terms:
            return "main", make_labeled_row(row, gold=["미래에너지산업과"], confidence="medium", evidence=energy_terms, note="환경 계열 카테고리이나 본문은 에너지 정책 문맥임")

    if category in {"제주특별자치도 에너지산업과", "기후에너지과"} and energy_terms:
        return "main", make_labeled_row(row, gold=["미래에너지산업과"], confidence="high", evidence=energy_terms, note="에너지산업 카테고리와 에너지 본문 근거가 일치")

    if category == "여성가족정책실 아이돌봄담당관":
        if childcare_terms:
            return "main", make_labeled_row(row, gold=["출산보육과"], confidence="medium", evidence=childcare_terms, note="아이돌봄 카테고리이나 본문은 어린이집/보육 업무에 가까움")
        if family_terms:
            return "main", make_labeled_row(row, gold=["여성가족과"], confidence="medium", evidence=family_terms, note="아이돌봄/가족 정책 본문 근거가 확인됨")
        return "review", make_review_row(row, confidence="needs_review", evidence=merge_evidence(childcare_terms, family_terms), note="아이돌봄 카테고리이나 보육/가족정책 축이 불명확함")

    # 비취약 카테고리는 기존 alias를 보존하되, 사람이 라벨링한 정답이 아님을 medium으로 표시한다.
    if old_gold and old_gold != [NONE_LABEL]:
        return "main", make_labeled_row(row, gold=old_gold, confidence="medium", evidence=[category], note="취약 alias 우선 정제 대상이 아니므로 기존 자동 alias를 보존")

    return "review", make_review_row(row, confidence="needs_review", evidence=[], note="기존 gold가 없거나 본문 기준 자동 확정 불가")


def validate_gold(rows: Sequence[Dict[str, Any]], department_names: set[str]) -> None:
    """생성된 gold가 마스터 부서명 또는 NONE인지 검증한다."""
    for row in rows:
        gold = row.get("gold", [])
        if gold == [NONE_LABEL]:
            continue
        invalid = [name for name in gold if name not in department_names]
        if invalid:
            raise ValueError(f"{row.get('id')} 마스터에 없는 gold: {invalid}")


def summarize_changes(
    original_rows: Sequence[Dict[str, Any]],
    main_rows: Sequence[Dict[str, Any]],
    review_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """라벨 변경 현황을 요약한다."""
    original_by_id = {row.get("id"): row for row in original_rows}
    confidence_counts = Counter(row.get("label_confidence", "") for row in main_rows)
    confidence_counts.update(row.get("label_confidence", "") for row in review_rows)
    source_counts = Counter(row.get("label_source", "") for row in main_rows)
    source_counts.update(row.get("label_source", "") for row in review_rows)

    changed: List[Dict[str, Any]] = []
    by_old_source: Dict[str, Counter[str]] = defaultdict(Counter)
    for row in main_rows:
        old = original_by_id.get(row.get("id"), {})
        old_gold = old.get("gold", [])
        old_source = str(old.get("label_source", ""))
        changed_flag = list(old_gold) != list(row.get("gold", []))
        if changed_flag:
            changed.append(row)
        by_old_source[old_source]["total_main"] += 1
        by_old_source[old_source]["changed"] += int(changed_flag)
        by_old_source[old_source][str(row.get("label_confidence", ""))] += 1
    for row in review_rows:
        old = original_by_id.get(row.get("id"), {})
        old_source = str(old.get("label_source", ""))
        by_old_source[old_source]["review"] += 1

    return {
        "total_original": len(original_rows),
        "total_main": len(main_rows),
        "total_review": len(review_rows),
        "confidence_counts": dict(confidence_counts),
        "source_counts": dict(source_counts),
        "changed_count": len(changed),
        "changed_samples": changed[:12],
        "by_old_source": {key: dict(counter) for key, counter in by_old_source.items()},
    }


def render_report(summary: Dict[str, Any], *, output_path: Path, review_path: Path, report_path: Path) -> str:
    """Markdown 보고서를 만든다."""
    target_sources = [
        "consulting_category_alias:건설과",
        "consulting_category_alias:도시활력지원과",
        "consulting_category_alias:녹색도시과",
        "consulting_category_alias:철도교통과",
        "consulting_category_alias:생활교통복지과",
        "consulting_category_alias:생태하천과",
        "consulting_category_alias:건축과",
        "consulting_category_alias:창업",
    ]

    lines = [
        "# responsible_unit holdout1000 content-aware 라벨링 보고서",
        "",
        "## 생성 결과",
        "",
        f"- original rows: {summary['total_original']}",
        f"- content-aware eval rows: {summary['total_main']}",
        f"- review rows: {summary['total_review']}",
        f"- changed labels in eval rows: {summary['changed_count']}",
        f"- output: `{output_path}`",
        f"- review: `{review_path}`",
        "",
        "## label_confidence 분포",
        "",
        "| label_confidence | count |",
        "| --- | ---: |",
    ]
    for key, value in sorted(summary["confidence_counts"].items()):
        lines.append(f"| {key} | {value} |")

    lines.extend([
        "",
        "## 취약 label_source별 정제 결과",
        "",
        "| old label_source | eval rows | changed | review | high | medium | none |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    by_old_source = summary["by_old_source"]
    for source in target_sources:
        stats = by_old_source.get(source, {})
        lines.append(
            f"| {source} | {stats.get('total_main', 0)} | {stats.get('changed', 0)} | "
            f"{stats.get('review', 0)} | {stats.get('high', 0)} | {stats.get('medium', 0)} | {stats.get('none', 0)} |"
        )

    lines.extend([
        "",
        "## 변경 라벨 대표 샘플",
        "",
    ])
    for row in summary["changed_samples"]:
        lines.extend([
            f"### {row.get('id')}",
            f"- category: {row.get('original_consulting_category')}",
            f"- old_gold: {row.get('old_gold')}",
            f"- new_gold: {row.get('gold')}",
            f"- confidence: {row.get('label_confidence')}",
            f"- evidence: {row.get('label_evidence')}",
            f"- note: {row.get('label_note')}",
            f"- query: {str(row.get('query', ''))[:220]}",
            "",
        ])

    lines.extend([
        "## 주의",
        "",
        "- 이 라벨셋은 자동 재정제 결과이며 최종 정답셋이 아니다.",
        "- 모델 예측 결과를 gold 생성 근거로 사용하지 않았다.",
        "- low/needs_review는 평가 본파일에서 제외하고 별도 검수 대상으로 분리했다.",
        "- 운영 추론 로직에는 이 라벨링 규칙을 섞지 않는다.",
        "",
    ])
    text = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return text


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI 인자를 정의한다."""
    parser = argparse.ArgumentParser(description="responsible_unit holdout1000 content-aware 라벨셋 생성")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI 진입점."""
    args = build_arg_parser().parse_args(argv)
    rows = load_jsonl(args.input)
    department_names = load_department_names(args.master)

    main_rows: List[Dict[str, Any]] = []
    review_rows: List[Dict[str, Any]] = []
    for row in rows:
        bucket, labeled = decide_content_aware_label(row)
        if bucket == "main":
            main_rows.append(labeled)
        else:
            review_rows.append(labeled)

    validate_gold(main_rows, department_names)
    write_jsonl(args.output, main_rows)
    write_jsonl(args.review_output, review_rows)
    summary = summarize_changes(rows, main_rows, review_rows)
    render_report(summary, output_path=args.output, review_path=args.review_output, report_path=args.report)

    print(json.dumps({
        "input": str(args.input),
        "output": str(args.output),
        "review_output": str(args.review_output),
        "report": str(args.report),
        **summary,
        "changed_samples": [
            {
                "id": row.get("id"),
                "old_gold": row.get("old_gold"),
                "gold": row.get("gold"),
                "label_confidence": row.get("label_confidence"),
                "label_evidence": row.get("label_evidence"),
            }
            for row in summary["changed_samples"]
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

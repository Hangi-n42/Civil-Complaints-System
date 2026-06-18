"""국민신문고 정책 Q&A detail JSON을 기존 processed 민원 형식으로 변환한다.

기존 `scripts/parse_consulting_data.py`와 `app/structuring/preprocessing.py`는
수정하지 않고, 새 수집 데이터(`scripts/data/raw_civil_policy_qna/details`)만
기존 processed 스키마에 맞춰 정규화한다.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_INPUT_DIR = Path("scripts/data/raw_civil_policy_qna/details")
DEFAULT_OUTPUT_PATH = Path("data/processed/civil_policy_qna_processed.json")
DEFAULT_FAILED_OUTPUT_PATH = Path("data/processed/civil_policy_qna_failed_records.json")

logger = logging.getLogger(__name__)


@dataclass
class CivilPolicyQnaRecord:
    source_id: str
    source: str
    consulting_date: str
    consulting_category: str
    title: str
    client_question: str
    consultant_answer: str
    consulting_turns: str
    original_length: int
    parsing_success: bool
    parsing_error: str | None = None


_BLOCK_TAG_RE = re.compile(r"(?i)<\s*/?\s*(?:br|p|div|li|tr|table|ul|ol|h[1-6])[^>]*>")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class PolicyCategoryRule:
    category: str
    strong_terms: tuple[str, ...]
    context_terms: tuple[str, ...] = ()
    min_score: int = 3


# 정책 Q&A 원천은 subjList가 대부분 비어 있어 기관/부서/제목/법령명 기반으로만 보수적으로 보강한다.
# 카테고리명은 부산시 분야별정보 대분류와 FE 세부태그 표현을 함께 쓰기 위해 "대분류 > 세부태그"로 둔다.
POLICY_CATEGORY_RULES: tuple[PolicyCategoryRule, ...] = (
    PolicyCategoryRule(
        "교통·물류 > 도로시설물",
        ("도로", "국도", "지방도", "도로점용", "보도", "교량", "터널", "가로등", "보안등", "포트홀"),
    ),
    PolicyCategoryRule(
        "교통·물류 > 자동차",
        ("자동차", "운전면허", "차량", "번호판", "검사", "등록원부", "말소등록"),
    ),
    PolicyCategoryRule("교통·물류 > 버스", ("버스", "노선", "정류장", "배차", "여객자동차")),
    PolicyCategoryRule("교통·물류 > 택시", ("택시", "개인택시", "택시운송")),
    PolicyCategoryRule("교통·물류 > 철도", ("철도", "도시철도", "지하철", "역사", "승강장")),
    PolicyCategoryRule("교통·물류 > 항공", ("항공", "공항", "비행", "항공기")),
    PolicyCategoryRule(
        "도시·건축·주택 > 건축허가",
        ("건축", "건축물", "건축허가", "대수선", "용도변경", "사용승인", "건폐율", "용적률"),
    ),
    PolicyCategoryRule(
        "도시·건축·주택 > 주택",
        ("주택", "공동주택", "아파트", "임대주택", "임대차", "장기수선", "관리규약"),
    ),
    PolicyCategoryRule(
        "도시·건축·주택 > 도시계획",
        ("도시계획", "개발행위", "지구단위계획", "토지이용계획", "공시지가", "지적", "토지"),
    ),
    PolicyCategoryRule(
        "도시·건축·주택 > 건설업",
        ("건설업", "전문건설", "종합건설", "하도급", "건설기계", "기계설비", "건설기술"),
    ),
    PolicyCategoryRule(
        "경제 > 세무",
        ("국세청", "세무", "세금", "사업자등록", "법인세", "부가가치세", "소득세", "종합소득세", "원천징수"),
        min_score=2,
    ),
    PolicyCategoryRule(
        "경제 > 소상공인",
        ("소상공인", "중소기업", "중소벤처", "전통시장", "상권", "자영업", "경영", "창업"),
        min_score=2,
    ),
    PolicyCategoryRule("경제 > 금융", ("금융", "대출", "보증", "신용", "보험", "카드")),
    PolicyCategoryRule(
        "일자리·노동·교육 > 교육",
        ("교육청", "교육부", "학교", "학생", "교원", "교사", "유치원", "학원", "수능", "연수", "학적"),
        min_score=2,
    ),
    PolicyCategoryRule(
        "일자리·노동·교육 > 노동",
        ("고용노동", "근로", "임금", "퇴직금", "노동", "산재", "실업급여", "근로계약", "휴가"),
        min_score=2,
    ),
    PolicyCategoryRule("일자리·노동·교육 > 일자리", ("채용", "취업", "구직", "직업훈련", "일자리")),
    PolicyCategoryRule(
        "사회복지 > 복지정책",
        ("복지", "기초생활", "생계급여", "의료급여", "주거급여", "긴급복지", "차상위"),
    ),
    PolicyCategoryRule("사회복지 > 노인복지", ("노인", "기초연금", "장기요양", "요양")),
    PolicyCategoryRule("사회복지 > 장애인복지", ("장애인", "장애", "전동휠체어", "보조기기")),
    PolicyCategoryRule("여성·가족 > 보육", ("어린이집", "보육", "영유아", "양육", "누리과정")),
    PolicyCategoryRule("여성·가족 > 가족", ("가족", "출산", "임신", "한부모", "다문화", "아동", "청소년")),
    PolicyCategoryRule(
        "보건·건강 > 식품",
        ("식품의약품안전처", "식품", "수입식품", "건강기능식품", "영업신고", "식품위생"),
        min_score=2,
    ),
    PolicyCategoryRule(
        "보건·건강 > 의약",
        ("의약품", "의료기기", "약국", "마약류", "화장품", "한약", "처방전"),
    ),
    PolicyCategoryRule("보건·건강 > 건강정책", ("보건소", "건강", "치매", "검진", "예방접종", "금연")),
    PolicyCategoryRule("보건·건강 > 감염병", ("감염병", "코로나", "방역", "격리", "예방접종")),
    PolicyCategoryRule(
        "안전 > 생활안전",
        ("경찰청", "경찰", "범죄", "신고", "분실물", "교통사고", "층간소음", "생활안전"),
        min_score=2,
    ),
    PolicyCategoryRule("안전 > 사회재난", ("소방", "화재", "구조", "구급", "재난", "안전사고")),
    PolicyCategoryRule("안전 > 자연재난", ("태풍", "홍수", "침수", "폭우", "지진", "산사태")),
    PolicyCategoryRule(
        "공원녹지·환경 > 환경",
        ("환경부", "환경", "대기", "소음", "악취", "비산먼지", "폐수", "오염"),
        min_score=2,
    ),
    PolicyCategoryRule("공원녹지·환경 > 폐기물", ("폐기물", "쓰레기", "재활용", "분리배출", "음식물")),
    PolicyCategoryRule("공원녹지·환경 > 하천", ("하천", "하수", "상수도", "수질", "물환경", "배수")),
    PolicyCategoryRule("공원녹지·환경 > 공원", ("공원", "녹지", "산림", "등산로", "숲길")),
    PolicyCategoryRule(
        "해양농수산 > 해양수산",
        ("해양수산", "해양", "수산", "어업", "어선", "항만", "항로", "양식"),
        min_score=2,
    ),
    PolicyCategoryRule("해양농수산 > 농축산", ("농업", "축산", "농지", "농산물", "가축", "동물보호", "반려동물")),
    PolicyCategoryRule(
        "문화체육관광 > 문화유산",
        ("국가유산청", "문화유산", "문화재", "유적", "사적", "천연기념물"),
        min_score=2,
    ),
    PolicyCategoryRule("문화체육관광 > 관광", ("관광", "여행", "숙박", "야영장", "캠핑장")),
    PolicyCategoryRule("문화체육관광 > 문화예술", ("문화", "공연", "예술", "도서관", "박물관", "미술관")),
    PolicyCategoryRule("문화체육관광 > 체육", ("체육", "운동장", "체육시설", "스포츠")),
    PolicyCategoryRule(
        "행정 > 증명·민원",
        ("여권", "주민등록", "가족관계", "인감", "증명서", "정보공개", "행정심판"),
    ),
    PolicyCategoryRule("행정 > 공무원", ("공무원", "인사", "복무", "출장", "여비", "징계")),
    PolicyCategoryRule("행정 > 국방", ("국방", "방위사업", "군인", "병역", "입찰", "계약")),
    PolicyCategoryRule("행정 > 외교", ("외교", "비자", "영사", "재외국민")),
)


def clean_policy_text(value: Any) -> str:
    """HTML/엔티티가 섞인 API 본문을 기존 전처리 입력용 일반 텍스트로 정리한다."""
    if value is None:
        return ""

    text = str(value)
    for _ in range(2):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped

    text = text.replace("_x000D_", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\ufeff", "").replace("\u00a0", " ")
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_policy_date(value: Any) -> str:
    """YYYYMMDD 또는 YYYYMMDDHHMMSS 형태를 YYYY-MM-DD로 변환한다."""
    text = str(value or "").strip()
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _subject_name(item: Any) -> str:
    if isinstance(item, str):
        return clean_policy_text(item)
    if not isinstance(item, dict):
        return ""
    for key in (
        "subjNm",
        "subjName",
        "subjectName",
        "name",
        "title",
        "fullName",
    ):
        value = clean_policy_text(item.get(key))
        if value:
            return value
    return ""


def normalize_policy_category(subj_list: Any) -> str:
    """subjList가 있으면 주제명을 사용하고, 없으면 기존 관례대로 미분류로 둔다."""
    if isinstance(subj_list, list):
        names: list[str] = []
        for item in subj_list:
            name = _subject_name(item)
            if name and name not in names:
                names.append(name)
        if names:
            return " > ".join(names)
    return "미분류"


def _compact_for_match(value: Any) -> str:
    """규칙 매칭 시 공백/대소문자 차이를 줄인다."""
    return re.sub(r"\s+", "", clean_policy_text(value).casefold())


def _law_names(law_list: Any) -> list[str]:
    """lawList에서 법령명 텍스트만 안전하게 추출한다."""
    if not isinstance(law_list, list):
        return []
    names: list[str] = []
    for item in law_list:
        if not isinstance(item, dict):
            continue
        for key in ("lwrdNm", "fullName"):
            name = clean_policy_text(item.get(key))
            if name and name != "기타" and name not in names:
                names.append(name)
    return names


def _term_hits(text: str, terms: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        if _compact_for_match(term) in text:
            hits.append(term)
    return hits


def infer_policy_category(data: dict[str, Any]) -> str:
    """subjList가 없는 정책 Q&A의 카테고리를 원천 필드만으로 보수적으로 추론한다."""
    source_text = " ".join(
        clean_policy_text(data.get(key))
        for key in ("ancName", "deptName")
    )
    law_text = " ".join(_law_names(data.get("lawList")))
    title_question_text = " ".join(
        clean_policy_text(data.get(key))
        for key in ("qnaTitl", "qstnCntnCl")
    )

    weighted_fields = (
        (_compact_for_match(source_text), 2),
        (_compact_for_match(law_text), 3),
        (_compact_for_match(title_question_text), 3),
    )

    ranked: list[tuple[int, int, str]] = []
    for order, rule in enumerate(POLICY_CATEGORY_RULES):
        hits: list[str] = []
        score = 0
        for text, weight in weighted_fields:
            field_hits = _term_hits(text, rule.strong_terms)
            if field_hits:
                score += weight * len(field_hits)
                hits.extend(field_hits)
        if rule.context_terms:
            context_text = "".join(text for text, _weight in weighted_fields)
            context_hits = _term_hits(context_text, rule.context_terms)
            if not context_hits:
                continue
            hits.extend(context_hits)
        if score >= rule.min_score and hits:
            ranked.append((score, -order, rule.category))

    if not ranked:
        return "미분류"

    ranked.sort(reverse=True)
    return ranked[0][2]


def resolve_policy_category(data: dict[str, Any]) -> str:
    """원천 subjList를 우선하고, 없을 때만 추론 카테고리를 사용한다."""
    category = normalize_policy_category(data.get("subjList"))
    if category != "미분류":
        return category
    return infer_policy_category(data)


def extract_result_data(payload: Any) -> dict[str, Any]:
    """API envelope 또는 resultData 자체를 모두 받아 resultData dict를 반환한다."""
    if not isinstance(payload, dict):
        raise ValueError("JSON payload is not an object")
    if isinstance(payload.get("resultData"), dict):
        code = str(payload.get("resultCode") or "").strip()
        if code and code != "S00":
            raise ValueError(f"resultCode is not S00: {code}")
        return payload["resultData"]
    return payload


def convert_detail_payload(payload: dict[str, Any], *, fallback_source_id: str = "") -> CivilPolicyQnaRecord:
    """정책 Q&A detail payload 1건을 기존 processed 레코드 1건으로 변환한다."""
    try:
        data = extract_result_data(payload)
        source_id = clean_policy_text(data.get("faqNo")) or fallback_source_id
        source = clean_policy_text(data.get("ancName")) or clean_policy_text(data.get("deptName"))
        title = clean_policy_text(data.get("qnaTitl"))
        question = clean_policy_text(data.get("qstnCntnCl"))
        answer = clean_policy_text(data.get("ansCntnCl"))
        # 새 정책 Q&A 원천에는 답변이 비어 있는 소수 케이스가 있다.
        # 기존 구조화 어댑터는 title+client_question만으로도 동작하므로 답변 공백만으로 실패 처리하지 않는다.
        parsing_success = bool(source_id and source and (title or question))
        parsing_error = None if parsing_success else "required field is empty"

        return CivilPolicyQnaRecord(
            source_id=source_id,
            source=source,
            consulting_date=format_policy_date(data.get("regDate")),
            consulting_category=resolve_policy_category(data),
            title=title,
            client_question=question,
            consultant_answer=answer,
            consulting_turns="2" if answer else "1",
            original_length=len(question),
            parsing_success=parsing_success,
            parsing_error=parsing_error,
        )
    except Exception as exc:
        return CivilPolicyQnaRecord(
            source_id=fallback_source_id,
            source="",
            consulting_date="",
            consulting_category="미분류",
            title="처리실패",
            client_question="",
            consultant_answer="",
            consulting_turns="0",
            original_length=0,
            parsing_success=False,
            parsing_error=str(exc),
        )


def load_detail_file(path: Path) -> CivilPolicyQnaRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return convert_detail_payload(payload, fallback_source_id=path.stem)


def _iter_input_files(input_dir: Path, *, sample_size: int | None = None, seed: int = 42) -> list[Path]:
    files = sorted(input_dir.glob("*.json"))
    if sample_size is None or sample_size >= len(files):
        return files
    return sorted(random.Random(seed).sample(files, sample_size))


def process_detail_directory(input_dir: Path, *, sample_size: int | None = None, seed: int = 42) -> list[CivilPolicyQnaRecord]:
    files = _iter_input_files(input_dir, sample_size=sample_size, seed=seed)
    return [load_detail_file(path) for path in files]


def write_json_records(records: Iterable[CivilPolicyQnaRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {key: value for key, value in asdict(record).items() if value is not None}
        for record in records
    ]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _print_stats(records: list[CivilPolicyQnaRecord]) -> None:
    total = len(records)
    success = sum(1 for record in records if record.parsing_success)
    failed = total - success
    print({"total": total, "success": success, "failed": failed})
    if records:
        sample = next((record for record in records if record.parsing_success), records[0])
        print(
            {
                "sample_source_id": sample.source_id,
                "sample_source": sample.source,
                "sample_date": sample.consulting_date,
                "sample_category": sample.consulting_category,
                "sample_title": sample.title[:80],
                "sample_question": sample.client_question[:80],
                "sample_answer": sample.consultant_answer[:80],
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="국민신문고 정책 Q&A detail JSON을 기존 processed 민원 형식으로 변환"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--failed-output", type=Path, default=DEFAULT_FAILED_OUTPUT_PATH)
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    if not args.input.exists():
        raise FileNotFoundError(f"input directory not found: {args.input}")

    records = process_detail_directory(args.input, sample_size=args.sample_size, seed=args.seed)
    failed_records = [record for record in records if not record.parsing_success]
    _print_stats(records)

    if not args.dry_run:
        write_json_records(records, args.output)
        if failed_records:
            write_json_records(failed_records, args.failed_output)
        logger.info("saved %s", args.output)

    return 0 if not failed_records else 1


if __name__ == "__main__":
    raise SystemExit(main())

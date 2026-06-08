"""조문 파서 / 인용 검증 단위 테스트 (네트워크·모델 불필요)."""

from app.structuring.law_corpus import (
    format_article_no,
    parse_law_body,
    validate_citations,
)

# 법제처 lawService(target=law) 본문 응답을 모사한 샘플
SAMPLE_BODY = {
    "법령": {
        "기본정보": {"법령명_한글": "건축법", "법령ID": "001823"},
        "조문": {
            "조문단위": [
                {"조문번호": "1", "조문여부": "조문", "조문제목": "목적",
                 "조문내용": "제1조(목적) 이 법은 건축물의 ... 함을 목적으로 한다."},
                {"조문번호": "3", "조문가지번호": "2", "조문여부": "조문", "조문제목": "적용 제외",
                 "조문내용": "제3조의2(적용 제외) 다음 각 호의 건축물에는 ..."},
                {"조문번호": "2", "조문여부": "전문", "조문제목": "제1장 총칙", "조문내용": ""},
            ]
        },
    }
}
META = {"law_id": "001823", "name": "건축법", "doc_type": "law",
        "enforce_date": "20260227", "dept": "국토교통부"}


# ── format_article_no ─────────────────────────────────────────────────────
def test_format_article_no_variants():
    assert format_article_no("1") == "제1조"
    assert format_article_no("3", "2") == "제3조의2"
    assert format_article_no("10") == "제10조"
    assert format_article_no("000300") == "제3조"      # 6자리 코드
    assert format_article_no("000302") == "제3조의2"


# ── parse_law_body ────────────────────────────────────────────────────────
def test_parse_filters_non_articles_and_builds_records():
    recs = parse_law_body(META, SAMPLE_BODY, source_url="http://x/ID=001823")
    assert len(recs) == 2                              # 전문/빈 항목 제외
    r0 = recs[0]
    assert r0["law_id"] == "001823" and r0["law_name"] == "건축법"
    assert r0["article_no"] == "제1조"
    assert r0["doc_id"] == "law:001823:제1조"
    assert r0["doc_type"] == "law" and r0["dept"] == "국토교통부"
    assert r0["source_url"].endswith("ID=001823")
    assert recs[1]["article_no"] == "제3조의2"


def test_parse_handles_ordinance_root():
    body = {"자치법규": {"조문": {"조문단위": [
        {"조문번호": "1", "조문여부": "조문", "조문제목": "목적", "조문내용": "제1조(목적) ..."}
    ]}}}
    recs = parse_law_body({"law_id": "B1", "name": "부산광역시 주차장 조례", "doc_type": "ordinance"}, body)
    assert len(recs) == 1 and recs[0]["doc_type"] == "ordinance"
    assert recs[0]["doc_id"] == "ordinance:B1:제1조"


def test_parse_empty_or_malformed_returns_empty():
    assert parse_law_body(META, {}) == []
    assert parse_law_body(META, {"법령": {"조문": {"조문단위": []}}}) == []


# ── validate_citations (환각 방지) ────────────────────────────────────────
def _retrieved():
    return [
        {"law_name": "건축법", "article_no": "제3조", "law_id": "001823", "source_url": "u1"},
        {"law_name": "건설기계관리법", "article_no": "제26조", "law_id": "002999", "source_url": "u2"},
    ]


def test_validate_keeps_matches_and_flags_hallucinations():
    cites = [
        {"law_name": "건축법", "article_no": "제3조"},        # 일치
        {"law_name": "건축법", "article_no": "제99조"},       # 검색결과에 없음 → invalid
    ]
    out = validate_citations(cites, _retrieved())
    assert len(out["valid"]) == 1 and out["valid"][0]["source_url"] == "u1"
    assert out["valid"][0]["verified"] is True and out["valid"][0]["law_id"] == "001823"
    assert len(out["invalid"]) == 1 and out["invalid"][0]["verified"] is False


def test_validate_normalizes_article_and_law_spacing():
    cites = [{"law_name": "건축법", "article_no": "3조"},        # '제'/공백 변형
             {"law_name": " 건설기계관리법 ", "article_no": "제 26 조"}]
    out = validate_citations(cites, _retrieved())
    assert len(out["valid"]) == 2 and out["invalid"] == []


def test_validate_empty_inputs():
    assert validate_citations([], _retrieved()) == {"valid": [], "invalid": []}
    assert validate_citations([{"law_name": "X", "article_no": "제1조"}], []) == {
        "valid": [], "invalid": [{"law_name": "X", "article_no": "제1조", "verified": False}]}


# ── 자치법규 등 컨테이너 키 변형(0조문 버그 회귀 방지) ────────────────────
def test_parse_finds_articles_regardless_of_container_key():
    meta = {"law_id": "B1", "name": "부산광역시 ○○ 조례", "doc_type": "ordinance"}
    # 컨테이너 키가 '조', 더 깊은 중첩, 조문내용 없이 항만 — 모두 조문을 찾아야 한다
    v1 = {"자치법규": {"조": [
        {"조문번호": "1", "조문내용": "제1조(목적) ..."},
        {"조문번호": "2", "조문내용": "제2조(정의) ..."}]}}
    v2 = {"LawService": {"본문": {"조문정보": {"조문단위": [
        {"조문번호": "1", "조문제목": "목적", "조문내용": "제1조(목적) ..."}]}}}}
    v3 = {"자치법규": {"조문": {"조문단위": [
        {"조문번호": "3", "조문제목": "적용", "항": [{"항번호": "1", "항내용": "본문 ..."}]}]}}}
    assert len(parse_law_body(meta, v1)) == 2
    assert len(parse_law_body(meta, v2)) == 1
    assert len(parse_law_body(meta, v3)) == 1
    assert parse_law_body(meta, v3)[0]["doc_type"] == "ordinance"


def test_parse_ignores_hang_only_dicts():
    # 항(項) 단위 dict 가 리스트로 있어도 조문으로 오인하지 않는다
    body = {"자치법규": {"조문": {"조문단위": [
        {"조문번호": "1", "조문내용": "제1조 ...", "항": [
            {"항번호": "1", "항내용": "①..."}, {"항번호": "2", "항내용": "②..."}]}]}}}
    recs = parse_law_body({"law_id": "B", "name": "조례", "doc_type": "ordinance"}, body)
    assert len(recs) == 1 and recs[0]["article_no"] == "제1조"


def test_parse_handles_ordinance_field_name_variants():
    # 자치법규가 조문* 대신 조번호/조내용/조제목/조가지번호 를 쓰는 경우
    body = {"자치법규": {"조문": {"조": [
        {"조번호": "1", "조제목": "목적", "조내용": "제1조(목적) 이 조례는 ..."},
        {"조번호": "2", "조가지번호": "2", "조내용": "제2조의2 ..."}]}}}
    recs = parse_law_body({"law_id": "B1", "name": "부산광역시 ○○ 조례", "doc_type": "ordinance"}, body)
    assert [r["article_no"] for r in recs] == ["제1조", "제2조의2"]
    assert recs[0]["article_title"] == "목적"


# ── 실제 부산 자치법규 응답 형태(0조문 버그 최종 회귀) ────────────────────
# 핵심 차이: 조문여부="Y"(법령은 "조문"), 조문번호=리스트["000100", ...]
REAL_ORDIN_BODY = {
    "LawService": {
        "자치법규기본정보": {"자치법규ID": "2160706", "자치법규명": "○○ 조례",
                          "지자체기관명": "부산광역시", "시행일자": "20190710"},
        "부칙": {"부칙내용": "부칙 ..."},
        "조문": {"조": [
            {"조문번호": ["000100", "000100"], "조제목": "목적",
             "조내용": "제1조(목적) ...", "조문여부": "Y"},
            {"조문번호": ["001000", "001000"], "조제목": "홍보 등",
             "조내용": "제10조 ...", "조문여부": "Y"},
            {"조문번호": ["001100", "001100"], "조제목": "포상",
             "조내용": "제11조(포상) ...", "조문여부": "Y"},
        ]},
        "제개정이유": {"제개정이유내용": "..."},
    }
}


def test_parse_real_busan_ordinance_shape():
    meta = {"law_id": "2160706", "name": "○○ 조례", "doc_type": "ordinance",
            "dept": "부산광역시", "enforce_date": "20190710"}
    recs = parse_law_body(meta, REAL_ORDIN_BODY, source_url="http://x/ID=2160706")
    assert len(recs) == 3                                  # 조문여부="Y" 도 채택
    assert [r["article_no"] for r in recs] == ["제1조", "제10조", "제11조"]  # 6자리 코드
    assert recs[0]["article_title"] == "목적"
    assert recs[0]["doc_id"] == "ordinance:2160706:제1조"


def test_format_article_no_accepts_list():
    assert format_article_no(["000100", "000100"]) == "제1조"
    assert format_article_no(["001100"]) == "제11조"

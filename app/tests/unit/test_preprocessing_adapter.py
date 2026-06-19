"""전처리 어댑터의 민원 원문/검색용 본문 생성 테스트."""
from app.structuring.preprocessing import (
    civil_text,
    civil_text_with_answer,
    parse_consulting_content,
    process_raw_record,
    to_structuring_record,
)


def test_civil_text_combines_title_and_question():
    rec = {"title": "도로 파손", "client_question": "차가 망가졌어요"}
    assert civil_text(rec) == "도로 파손\n차가 망가졌어요"


def test_civil_text_uses_title_when_question_empty():
    rec = {"title": "1번 출구 공사 불편", "client_question": ""}
    assert civil_text(rec) == "1번 출구 공사 불편"


def test_civil_text_no_duplicate_when_q_starts_with_title():
    rec = {"title": "민원", "client_question": "민원 내용 본문"}
    assert civil_text(rec) == "민원 내용 본문"


def test_civil_text_excludes_consultant_answer():
    rec = {"title": "T", "client_question": "Q본문", "consultant_answer": "상담사 답변 A"}
    assert "상담사" not in civil_text(rec)


def test_civil_text_with_answer_includes_consultant_answer():
    rec = {"title": "T", "client_question": "Q본문", "consultant_answer": "상담사 답변 A"}

    text = civil_text_with_answer(rec)

    assert text == "T\nQ본문\n상담사 답변 A"


def test_to_structuring_record_maps_fields():
    rec = {"source_id": 2000001, "title": "T", "client_question": "Q",
           "consultant_answer": "A", "consulting_category": "행정과", "source": "경상남도",
           "consulting_date": "2022-08-02"}
    out = to_structuring_record(rec)
    assert out["case_id"] == "2000001"
    assert out["text"] == "T\nQ"
    assert out["category"] == "행정과"
    assert out["region"] == "경상남도"


def test_category_defaults_to_미분류():
    out = to_structuring_record({"source_id": "1", "client_question": "Q", "consulting_category": ""})
    assert out["category"] == "미분류"


def test_parse_consulting_content_standard_title_qa():
    content = "제목 : 도로 파손\n\nQ : 도로에 포트홀이 생겼습니다.\n\nA : 현장 확인하겠습니다."

    parsed = parse_consulting_content(content)

    assert parsed["title"] == "도로 파손"
    assert parsed["client_question"] == "도로에 포트홀이 생겼습니다."
    assert parsed["consultant_answer"] == "현장 확인하겠습니다."


def test_parse_consulting_content_accepts_marker_variants_and_x000d():
    content = "Q. 어린이집 보조금 문의_x000D_\nA: 담당 부서에서 검토 예정입니다."

    parsed = parse_consulting_content(content)

    assert parsed["client_question"] == "어린이집 보조금 문의"
    assert parsed["consultant_answer"] == "담당 부서에서 검토 예정입니다."


def test_parse_consulting_content_dialogue_customer_only_question():
    content = (
        "상담원: 안녕하십니까. 무엇을 도와드릴까요?\n"
        "고객: 브런치 콘서트 단체 예매가 가능한가요?\n"
        "상담원: 단체 사전 예매는 어렵습니다.\n"
        "고객: 예매 오픈일은 언제인가요?"
    )

    parsed = parse_consulting_content(content, source="국립아시아문화전당")

    assert parsed["title"] == "브런치 콘서트 단체 예매가 가능한가요?"
    assert parsed["client_question"] == "브런치 콘서트 단체 예매가 가능한가요?\n예매 오픈일은 언제인가요?"
    assert parsed["consultant_answer"] == "안녕하십니까. 무엇을 도와드릴까요?\n단체 사전 예매는 어렵습니다."


def test_civil_text_parses_raw_content_without_answer():
    rec = {
        "consulting_content": "제목 : 보안등 고장\n\nQ : 골목 보안등이 꺼졌습니다.\n\nA : 접수했습니다.",
    }

    text = civil_text(rec)

    assert text == "보안등 고장\n골목 보안등이 꺼졌습니다."
    assert "접수했습니다" not in text


def test_to_structuring_record_accepts_raw_consulting_content():
    rec = {
        "source_id": 123,
        "source": "서울시",
        "consulting_date": "20240102",
        "consulting_category": "",
        "consulting_length": 50,
        "consulting_content": "Q : 음식물 쓰레기 수거 기준이 궁금합니다.\n\nA : 안내드립니다.",
    }

    out = to_structuring_record(rec)

    assert out["case_id"] == "123"
    assert out["text"] == "음식물 쓰레기 수거 기준이 궁금합니다."
    assert out["category"] == "미분류"
    assert out["region"] == "서울시"
    assert out["created_at"] == "2024-01-02"
    assert out["metadata"]["original_length"] == 50


def test_process_raw_record_keeps_processed_shape():
    raw = {
        "source_id": "acc-1",
        "source": "국립아시아문화전당",
        "consulting_date": "20240203",
        "consulting_category": "문화",
        "consulting_turns": 2,
        "consulting_length": 100,
        "consulting_content": "고객: 전시 관람 시간이 궁금합니다.\n상담원: 10시부터 운영합니다.",
    }

    processed = process_raw_record(raw)

    assert processed["consulting_date"] == "2024-02-03"
    assert processed["title"] == "전시 관람 시간이 궁금합니다."
    assert processed["client_question"] == "전시 관람 시간이 궁금합니다."
    assert processed["consultant_answer"] == "10시부터 운영합니다."
    assert processed["parsing_success"] is True


def test_process_raw_record_unwraps_policy_qna_result_data():
    raw = {
        "resultCode": "S00",
        "resultData": {
            "faqNo": 6899257,
            "ancName": "방위사업청",
            "deptName": "방위사업청 방위사업정책국 표준기획과",
            "regDate": "20251223",
            "qnaTitl": "방위사업청 행정규칙에 관한 질의",
            "qstnCntnCl": "공개등급 기준이 궁금합니다.&lt;br /&gt;확인 부탁드립니다.",
            "ansCntnCl": "안녕하십니까?&lt;br /&gt;검토 결과를 안내드립니다.",
        },
    }

    processed = process_raw_record(raw)

    assert processed["source_id"] == "6899257"
    assert processed["source"] == "방위사업청"
    assert processed["consulting_date"] == "2025-12-23"
    assert processed["consulting_category"] == "방위사업청 방위사업정책국 표준기획과"
    assert processed["title"] == "방위사업청 행정규칙에 관한 질의"
    assert processed["client_question"] == "공개등급 기준이 궁금합니다.\n확인 부탁드립니다."
    assert processed["consultant_answer"] == "안녕하십니까?\n검토 결과를 안내드립니다."
    assert processed["parsing_success"] is True


def test_to_structuring_record_accepts_policy_qna_wrapper_directly():
    raw = {
        "resultData": {
            "faqNo": "6899311",
            "ancName": "방위사업청",
            "deptName": "방위사업청 방위산업진흥국 방산정책과",
            "regDate": "20251223",
            "qnaTitl": "군용화약류 운반책임자 유권해석 요청",
            "qstnCntnCl": "운반책임자 지정 범위를 알려주세요.",
            "ansCntnCl": "답변 본문",
        }
    }

    out = to_structuring_record(raw)

    assert out["case_id"] == "6899311"
    assert out["text"] == "군용화약류 운반책임자 유권해석 요청\n운반책임자 지정 범위를 알려주세요."
    assert out["category"] == "방위사업청 방위산업진흥국 방산정책과"
    assert out["region"] == "방위사업청"
    assert out["created_at"] == "2025-12-23"

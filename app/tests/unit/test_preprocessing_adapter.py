"""전처리 어댑터(민원인 원문 분리) 테스트."""
from app.structuring.preprocessing import civil_text, to_structuring_record


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


def test_to_structuring_record_maps_fields():
    rec = {"source_id": 2000001, "title": "T", "client_question": "Q",
           "consulting_category": "행정과", "source": "경상남도",
           "consulting_date": "2022-08-02"}
    out = to_structuring_record(rec)
    assert out["case_id"] == "2000001"
    assert out["text"] == "T\nQ"
    assert out["category"] == "행정과"
    assert out["region"] == "경상남도"


def test_category_defaults_to_미분류():
    out = to_structuring_record({"source_id": "1", "client_question": "Q", "consulting_category": ""})
    assert out["category"] == "미분류"

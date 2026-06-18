from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.preprocess_civil_policy_qna import (
    clean_policy_text,
    convert_detail_payload,
    format_policy_date,
    infer_policy_category,
    load_detail_file,
    normalize_policy_category,
    resolve_policy_category,
)


def test_clean_policy_text_removes_html_tags_and_entities():
    raw = "&lt;div&gt;안녕하세요.&lt;br /&gt;&amp;nbsp;사업자등록 안내입니다.&lt;/div&gt;"

    assert clean_policy_text(raw) == "안녕하세요.\n사업자등록 안내입니다."


def test_convert_detail_payload_matches_processed_schema():
    payload = {
        "resultCode": "S00",
        "resultData": {
            "faqNo": "500918",
            "dutySctnNm": "tqapttn",
            "qnaTitl": "법인의 사업자등록 여부",
            "qstnCntnCl": "사업자등록을 해야 되는지 알고 싶어 문의드립니다.",
            "ansCntnCl": "&lt;p&gt;6월4일까지 법인 설립 신고 및 사업자등록 신청을 하셔야 합니다.&lt;/p&gt;",
            "ancName": "중소벤처기업부",
            "deptName": "중소벤처기업부 담당부서",
            "regDate": "20110420",
            "ancCode": "1421000",
            "deptCode": "1421010",
            "lawList": [],
            "subjList": [],
        },
    }

    record = convert_detail_payload(payload)

    assert record.source_id == "500918"
    assert record.source == "중소벤처기업부"
    assert record.consulting_date == "2011-04-20"
    assert record.consulting_category == "경제 > 세무"
    assert record.title == "법인의 사업자등록 여부"
    assert record.client_question == "사업자등록을 해야 되는지 알고 싶어 문의드립니다."
    assert record.consultant_answer == "6월4일까지 법인 설립 신고 및 사업자등록 신청을 하셔야 합니다."
    assert record.consulting_turns == "2"
    assert record.original_length == len(record.client_question)
    assert record.parsing_success is True
    assert record.parsing_error is None


def test_load_detail_file_handles_api_envelope(tmp_path: Path):
    path = tmp_path / "123.json"
    path.write_text(
        json.dumps(
            {
                "resultCode": "S00",
                "resultMessage": "OK",
                "resultData": {
                    "faqNo": "123",
                    "dutySctnNm": "tqapttn",
                    "qnaTitl": "공원 이용 문의",
                    "qstnCntnCl": "공원 이용 시간이 궁금합니다.",
                    "ansCntnCl": "공원 이용 시간은 현장 안내를 확인해 주세요.",
                    "ancName": "부산광역시",
                    "deptName": "부산광역시 공원부서",
                    "regDate": "20260618",
                    "ancCode": "0",
                    "deptCode": "0",
                    "lawList": [],
                    "subjList": [],
                },
                "resultDebug": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    record = load_detail_file(path)

    assert record.source_id == "123"
    assert record.consulting_date == "2026-06-18"
    assert record.parsing_success is True


def test_category_uses_subjects_when_present_and_falls_back_to_unclassified():
    assert normalize_policy_category([]) == "미분류"
    assert normalize_policy_category([{"subjNm": "경영 전략"}, {"subjNm": "세무"}]) == "경영 전략 > 세무"


def test_category_resolution_preserves_source_subjects_before_inference():
    payload = {
        "subjList": [{"subjNm": "원천분류"}, {"subjNm": "세부"}],
        "ancName": "국세청",
        "deptName": "국세청",
        "qnaTitl": "사업자등록 문의",
    }

    assert resolve_policy_category(payload) == "원천분류 > 세부"


def test_policy_category_inference_uses_department_and_law_signals():
    payload = {
        "ancName": "식품의약품안전처",
        "deptName": "식품의약품안전처 수입식품안전정책국 수입식품정책과",
        "qnaTitl": "샘플 판매 가능 여부",
        "qstnCntnCl": "수입식품 샘플을 판매할 수 있는지 궁금합니다.",
        "ansCntnCl": "",
        "lawList": [{"lwrdNm": "수입식품안전관리 특별법"}],
        "subjList": [],
    }

    assert infer_policy_category(payload) == "보건·건강 > 식품"


def test_policy_category_inference_keeps_weak_signal_unclassified():
    payload = {
        "ancName": "알 수 없는 기관",
        "deptName": "민원담당",
        "qnaTitl": "처리 기준 문의",
        "qstnCntnCl": "처리 기준이 궁금합니다.",
        "ansCntnCl": "담당 기관에 문의하시기 바랍니다.",
        "lawList": [],
        "subjList": [],
    }

    assert infer_policy_category(payload) == "미분류"


def test_format_policy_date_accepts_list_timestamp_shape():
    assert format_policy_date("20260616202337") == "2026-06-16"
    assert format_policy_date("20110420") == "2011-04-20"


def test_empty_answer_is_still_success_when_question_exists():
    record = convert_detail_payload(
        {
            "resultCode": "S00",
            "resultData": {
                "faqNo": "6893522",
                "qnaTitl": "층간소음 분쟁 발생 시 어떻게 해야 하나요?",
                "qstnCntnCl": "층간소음 분쟁 발생 시 어떻게 해야 하나요?",
                "ansCntnCl": "",
                "ancName": "경찰청",
                "deptName": "경찰청 담당부서",
                "regDate": "20250721",
                "subjList": [],
            },
        }
    )

    assert record.parsing_success is True
    assert record.consultant_answer == ""
    assert record.consulting_turns == "1"

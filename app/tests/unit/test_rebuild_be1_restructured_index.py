from __future__ import annotations

from scripts.rebuild_be1_restructured_index import _extract_civil_source_text


def test_extract_civil_source_text_prefers_search_text_over_structuring_text():
    text, parse_mode = _extract_civil_source_text(
        {"consulting_content": "Q : 도로 파손\nA : 담당 부서에 전달했습니다."},
        {
            "raw_text": "도로 파손",
            "text": "도로 파손",
            "search_text": "도로 파손\n담당 부서에 전달했습니다.",
        },
    )

    assert text == "도로 파손 담당 부서에 전달했습니다."
    assert parse_mode == "search_text_with_answer"

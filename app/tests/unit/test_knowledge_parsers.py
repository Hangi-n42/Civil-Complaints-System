"""Small format/scope checks, with the selected local corpus when available."""
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.knowledge.parsers import parse_unit, plan_units

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "configs/knowledge/pilot_v1/sources.json"


@pytest.mark.parametrize('separator', ['\n', '다음 표 설명\n'])
def test_markdown_table_headers_reset_between_tables(tmp_path, separator):
    path = tmp_path / 'tables.md'
    text = ('# 자료\n| 단지 | 세대수 |\n| --- | --- |\n| A | 100 |\n'
            + separator + '| 공고 | 접수일 |\n| --- | --- |\n| B | 2026-09-30 |\n')
    path.write_text(text, encoding='utf-8')
    blocks = parse_unit(path, 'md', plan_units(path, 'md')[0])
    first = next(b for b in blocks if '| A |' in b['text'])
    second = next(b for b in blocks if '| B |' in b['text'])
    assert first['locator']['table_headers'] == ['| 단지 | 세대수 |']
    assert second['locator']['table_headers'] == ['| 공고 | 접수일 |']
    for block in blocks:
        loc = block['locator']
        assert loc['section'] == '# 자료'
        assert text[loc['start_char']:loc['end_char']] == block['text']


def test_html_table_positions_and_empty_body(tmp_path):
    path = tmp_path / "table.html"
    path.write_text('<body>outside<div id="content"><table><tr><th rowspan="2">유형</th><td>A</td></tr><tr><td>B</td></tr></table></div><script>wrong</script></body>')
    units = plan_units(path, "html", {"selector": "#content"})
    blocks = parse_unit(path, "html", units[0])
    assert [b["text"] for b in blocks] == ["유형", "A", "B"]
    assert blocks[0]["locator"]["merged_span"] == {"rows": 2, "columns": 1}
    assert (blocks[2]["locator"]["row"], blocks[2]["locator"]["column"]) == (1, 1)
    path.write_text('<body><div id="content"></div></body>')
    with pytest.raises(ValueError, match="추출 텍스트 없음"):
        parse_unit(path, "html", units[0])


def test_csv_scope_and_missing_code(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("단지코드,단지명\nC1,첫째\nC2,둘째\n", encoding="utf-8-sig")
    units = plan_units(path, "csv", {"knowledge_input_complex_codes": ["C2"]})
    blocks = parse_unit(path, "csv", units[0])
    assert len(units) == 1 and blocks[0]["locator"]["physical_row"] == 3
    assert blocks[0]["locator"]["official_code"] == "C2"
    with pytest.raises(ValueError, match="선택 코드 누락"):
        missing = plan_units(path, "csv", {"knowledge_input_complex_codes": ["missing"]})
        parse_unit(path, "csv", missing[0])


def test_csv_file_checkpoint_reads_rows_once(tmp_path, monkeypatch):
    from app.knowledge import parsers
    path = tmp_path / 'cp949.csv'
    path.write_bytes('유형,이름\n국민임대,첫째\n분양전환,둘째\n'.encode('cp949'))
    original, calls = parsers._csv_rows, []
    def counted(*args):
        calls.append(args)
        yield from original(*args)
    monkeypatch.setattr(parsers, '_csv_rows', counted)
    units = plan_units(path, 'csv', {'encoding': 'cp949'})
    blocks = [b for unit in units for b in parse_unit(path, 'csv', unit)]
    assert len(calls) == 1 and len(units) == 1 and len(blocks) == 2
    assert [b['locator']['physical_row'] for b in blocks] == [2, 3]


def test_hwpx_registered_unit_preserves_member_and_paragraph(tmp_path):
    path = tmp_path / 'example.hwpx'
    with ZipFile(path, 'w') as archive:
        archive.writestr('Contents/section0.xml',
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
            'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            '<hp:p><hp:run><hp:t>시험 근거</hp:t></hp:run></hp:p></hs:sec>')
    unit = plan_units(path, 'hwpx')[0]
    block = parse_unit(path, 'hwpx', unit)[0]
    assert block['text'] == '시험 근거'
    assert block['locator']['member'] == 'Contents/section0.xml'
    assert block['locator']['xml_path'] == 'sec/p'


@pytest.mark.skipif(not (ROOT / "data/knowledge/pilot_v1/raw/qa_2026.hwpx").exists(), reason="Local selected originals are not distributed in Git")
def test_selected_sources_preserve_locations_and_scope():
    sources = json.loads(MANIFEST.read_text())["sources"]
    parsed = {}
    for source in sources:
        path = ROOT / source["raw_path"]
        format = source["format"].lower()
        units = plan_units(path, format, source["corpus_scope"])
        blocks = [b for unit in units for b in parse_unit(path, format, unit)]
        assert blocks and all(b["text"].strip() and b["locator"]["format"] == format for b in blocks)
        parsed[source["source_id"]] = blocks
        if format == "pdf":
            assert max(b["locator"]["physical_page"] for b in blocks) == 6
            assert all(b["locator"]["bbox"] for b in blocks)
    html = parsed["notice_correction2_html"]
    assert any("985" in b["text"] and b["locator"].get("official_code") == "C02748" for b in html)
    csv = parsed["complex_registry_csv"]
    assert len(csv) == 6 and {b["locator"]["official_code"] for b in csv} == {"C00446", "C01643", "C01951", "C01953", "C02715", "C02748"}
    table = parsed["LH-GUIDE-1025"]
    issuer = next(b for b in table if b["text"] == "각 지방 중소벤처기업청")
    assert (issuer["locator"]["row"], issuer["locator"]["column"]) == (5, 2)
    hwpx = parsed["LH-QA-2026"]
    assert not any("주거급여" in b["text"] for b in hwpx)
    assert any(b["locator"]["element_preorder_index_zero_based"] == 521 and "공공분양주택" in b["text"] for b in hwpx)
    assert any(b["locator"]["element_preorder_index_zero_based"] == 86 and "2026.03" in b["text"] for b in hwpx)
    dates = []
    for sid, date in [("notice_correction1_pdf", "2026.07.15"), ("notice_correction2_pdf", "2026.09.15")]:
        found = [b for b in parsed[sid] if b["locator"].get("printed_page") == 11 and date in b["text"]]
        assert found and all(b["locator"]["side"] == "left" for b in found)
        dates.append(found[0]["text"])
    assert dates[0] != dates[1]

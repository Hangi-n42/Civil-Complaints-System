"""Location-preserving adapters for registered source formats.

Units are serializable checkpoints; parsers read local registered originals only.
No model calls, inferred facts, JavaScript execution, or OCR fallbacks.
"""
from __future__ import annotations

import csv
import re
from importlib.metadata import version
from pathlib import Path
from typing import Any


def parser_info(format: str) -> dict:
    packages = {"pdf": "pdfplumber", "html": "beautifulsoup4", "hwpx": "python-hwpx"}
    if format == "csv":
        return {"name": "stdlib.csv", "version": "1", "adapter_version": "2"}
    if format in {'json', 'xlsx'}:
        return {'name': 'stdlib.json' if format == 'json' else 'stdlib.zipfile+xml', 'version': '1', 'adapter_version': '1'}
    if format in {"txt", "md"}:
        return {"name": "stdlib.text", "version": "1", "adapter_version": "2"}
    if format not in packages:
        raise ValueError(f"지원하지 않는 형식: {format}")
    return {"name": packages[format], "version": version(packages[format]), "adapter_version": "2" if format == "html" else "1"}


def _csv_rows(path: Path, encoding="utf-8-sig"):
    with path.open(encoding=encoding, newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"CSV 열 수 불일치: 행 {reader.line_num}")
            yield reader.line_num, row


def _text_blocks(path: Path, format: str):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        text = stream.read()
    section, headers, offset = '', [], 0
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        if not line.startswith('|'):
            headers = []
        if line.startswith('#'):
            section, headers = line.strip(), []
        if line.startswith('|') and not headers:
            headers = [line.strip()]
        # ponytail: literal spans preserve excerpts; semantic grouping belongs to discovery A2.
        for start in range(0, len(line), 2000):
            part = line[start:start + 2000]
            if part.strip():
                yield dict(text=part, locator=dict(format=format, line=line_number,
                           start_char=offset + start, end_char=offset + start + len(part),
                           section=section, table_headers=headers if line.startswith('|') else []))
        offset += len(line)


def _html(path: Path):
    from bs4 import BeautifulSoup
    return BeautifulSoup(path.read_text(encoding="utf-8-sig"), "html.parser")


def _sbd_records(text: str):
    # Only this named public metadata array is accepted, never arbitrary script objects.
    for match in re.finditer(r"\bsbdList\.push\(\s*\{(.*?)\}\s*\)", text, re.S):
        fields = dict(re.findall(r"\b(\w+)\s*:\s*'((?:\\.|[^'\\])*)'", match.group(1)))
        if not fields.get("sbdLgoNo"):
            raise ValueError("sbdList 단지 코드 누락")
        yield match, fields


def _hwpx_blocks(path: Path) -> list[dict]:
    from hwpx import TextExtractor
    blocks = []
    with TextExtractor(path) as extractor:
        for section in extractor.iter_sections():
            elements = list(section.element.iter())
            indices = {node: i for i, node in enumerate(elements)}
            parents = {child: node for node in elements for child in node}
            for paragraph in extractor.iter_paragraphs(section):
                text = paragraph.text(object_behavior="skip", preserve_breaks=True)
                if not text.strip():
                    continue
                locator = {"format": "hwpx", "member": section.name,
                           "element_preorder_index_zero_based": indices[paragraph.element],
                           "xml_path": paragraph.path, "paragraph_index": paragraph.index}
                node = paragraph.element
                while node in parents:
                    node = parents[node]
                    tag = node.tag.rsplit("}", 1)[-1]
                    if tag == "tc" and "cell" not in locator:
                        addr = next((n for n in node if n.tag.endswith("}cellAddr")), None)
                        span = next((n for n in node if n.tag.endswith("}cellSpan")), None)
                        locator["cell"] = indices[node]
                        if addr is not None:
                            locator.update(row=int(addr.get("rowAddr", 0)), column=int(addr.get("colAddr", 0)))
                        if span is not None:
                            locator["merged_span"] = {"rows": int(span.get("rowSpan", 1)), "columns": int(span.get("colSpan", 1))}
                    if tag == "tbl" and "table" not in locator:
                        locator["table"] = indices[node]
                        locator["table_shape"] = [int(node.get("rowCnt", 0)), int(node.get("colCnt", 0))]
                blocks.append({"text": text, "locator": locator})
    return blocks


def plan_units(path: Path, format: str, scope: dict | str | None = None) -> list[dict]:
    parser_info(format)
    if isinstance(scope, str):
        if format == "html" and scope == "#cntntsView 본문":
            scope = {"selector": "#cntntsView"}
        else:
            raise ValueError("구조화된 추출 범위를 입력하세요")
    scope = scope or {}
    if format in {'json', 'xlsx'}:
        return [{'id': 'table', 'locator': {'format': format}, 'scope': scope}]
    if format in {"txt", "md"}:
        return [{"id": "text", "locator": {"format": format}}]
    if format == "pdf":
        import pdfplumber
        with pdfplumber.open(path) as document:
            start, end = scope.get("physical_pages_inclusive", [1, len(document.pages)])
            if not (1 <= start <= end <= len(document.pages)):
                raise ValueError("PDF 페이지 범위가 원문을 벗어납니다")
            two_up = scope.get("two_up", "2면" in scope.get("page_layout", ""))
            printed = scope.get("printed_pages_inclusive", [None])[0]
            units = []
            for page in range(start, end + 1):
                for side in (["left", "right"] if two_up else ["full"]):
                    locator = {"format": format, "physical_page": page, "side": side}
                    if printed is not None:
                        locator["printed_page"] = printed + (page - start) * (2 if two_up else 1) + (side == "right")
                    units.append({"id": f"page-{page}-{side}", "locator": locator})
            return units
    if format == "csv":
        # One file checkpoint avoids reading the entire CSV once per row.
        return [{"id": "csv", "locator": {"format": format}, "scope": scope}]
    if format == "html":
        soup = _html(path)
        codes = scope.get("complex_codes")
        selectors = ["#sub_container > section:nth-of-type(1)", "#sub_container > section:nth-of-type(2)"] if codes else [scope.get("selector", "body")]
        units = []
        for selector in selectors:
            nodes = soup.select(selector)
            if not nodes:
                raise ValueError(f"HTML 본문 없음: {selector}")
            for index in range(len(nodes)):
                units.append({"id": f"html-{len(units)}", "locator": {"format": format, "selector": selector, "element_index": index}})
        if codes:
            records = list(_sbd_records(path.read_text(encoding="utf-8-sig")))
            found = {fields["sbdLgoNo"] for _, fields in records}
            if set(codes) - found:
                raise ValueError("HTML sbdList 선택 코드 누락")
            for code in codes:
                units.append({"id": f"complex-{code}", "locator": {"format": format, "script_array": "sbdList", "official_code": code}})
        return units
    blocks = _hwpx_blocks(path)
    if scope.get("include"):
        if scope["include"] != "임대주택 Q1~Q16":
            raise ValueError("지원하는 HWPX 선택 범위는 임대주택 Q1~Q16입니다")
        heading = next((i for i, b in enumerate(blocks) if b["text"].strip() == "임대주택"), None)
        if heading is None:
            raise ValueError("HWPX 임대주택 구역 없음")
        heading_shape = blocks[heading]["locator"].get("table_shape")
        end = next((i for i in range(heading + 1, len(blocks)) if blocks[i]["locator"].get("table_shape") == heading_shape), len(blocks))
        selected = blocks[heading + 1:end]
        questions = [(i, int(m.group(1))) for i, b in enumerate(selected) if (m := re.match(r"Q(\d+)\.", b["text"].strip()))]
        if [q for _, q in questions] != list(range(1, 17)):
            raise ValueError("HWPX 임대 Q1~Q16 경계 확인 실패")
        units = []
        for n, (begin, question) in enumerate(questions):
            finish = questions[n + 1][0] if n + 1 < len(questions) else len(selected)
            locators = [b["locator"] for b in selected[begin:finish]]
            units.append({"id": f"rental-q{question}", "locator": {"format": format, "section": f"임대주택 Q{question}"}, "paragraphs": locators})
        metadata = scope.get("metadata_include")
        if metadata:
            matches = [b for b in blocks if b["locator"]["member"] == metadata["hwpx_member"] and b["locator"]["element_preorder_index_zero_based"] == metadata["element_preorder_index_zero_based"]]
            if len(matches) != 1 or metadata["quote"] not in matches[0]["text"]:
                raise ValueError("HWPX 표지 기준월 근거 불일치")
            units.insert(0, {"id": "cover-metadata", "locator": {"format": format, "section": "표지 기준월"}, "paragraphs": [matches[0]["locator"]]})
        return units
    members = dict.fromkeys(b["locator"]["member"] for b in blocks)
    if not members:
        raise ValueError("HWPX 추출 가능한 문단 없음")
    return [{"id": f"section-{i}", "locator": {"format": format, "member": member}} for i, member in enumerate(members)]


def _html_blocks(path: Path, unit: dict) -> list[dict]:
    from bs4 import Comment, NavigableString, Tag
    locator = unit["locator"]
    if locator.get("script_array"):
        records = [(m, f) for m, f in _sbd_records(path.read_text(encoding="utf-8-sig")) if f["sbdLgoNo"] == locator["official_code"]]
        if len(records) != 1:
            raise ValueError("공식 단지 metadata 중복 또는 누락")
        match, fields = records[0]
        blocks = [{"text": "\n".join(f"{key}: {value}" for key, value in fields.items()), "locator": {**locator, "source_start_char": match.start(), "source_end_char": match.end(), "fields": fields}}]
        # LH's accessible image descriptions are stored with an explicit complex code.
        # Accept only this record shape and field; never interpret arbitrary JavaScript.
        for image in re.finditer(r'list\.push\("\{([^"\n]*?)\}"\)', path.read_text(encoding="utf-8-sig")):
            record = image.group(1)
            code = re.search(r"(?:^|, )sbdLgoNo=(C\d+)(?:,|$)", record)
            description = re.search(r"(?:^|, )imgAhflDesc=(.*)$", record)
            if code and description and code.group(1) == locator["official_code"]:
                from bs4 import BeautifulSoup
                text = BeautifulSoup(description.group(1), "html.parser").get_text("\n", strip=True)
                if text:
                    blocks.append({"text": text, "locator": {**locator, "script_array": "list:complex_image", "field": "imgAhflDesc", "source_start_char": image.start(), "source_end_char": image.end()}})
        return blocks
    soup = _html(path)
    root = soup.select(locator["selector"])[locator["element_index"]]
    blocks = []
    def emit(text: str, extra: dict):
        if text.strip():
            blocks.append({"text": text, "locator": {**locator, **extra}})
    def walk(node: Any, css: str):
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            emit(str(node), {"element_path": css})
            return
        if not isinstance(node, Tag) or node.name in {"script", "style", "button", "input", "noscript"}:
            return
        if re.fullmatch(r"h[1-6]", node.name):
            emit(node.get_text("\n", strip=True), {"element_path": css, "heading_level": int(node.name[1])})
            return
        if node.name == "img":
            emit(node.get("alt", ""), {"element_path": css, "attribute": "alt"})
            return
        if node.name == "table":
            caption = node.find("caption")
            occupied = set()
            for row_index, row in enumerate(node.find_all("tr")):
                column = 0
                for cell in row.find_all(["td", "th"], recursive=False):
                    while (row_index, column) in occupied:
                        column += 1
                    rows, columns = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
                    occupied.update((r, c) for r in range(row_index, row_index + rows) for c in range(column, column + columns))
                    emit(cell.get_text("\n", strip=True), {"element_path": css, "table_caption": caption.get_text(" ", strip=True) if caption else None, "row": row_index, "column": column, "merged_span": {"rows": rows, "columns": columns}})
                    column += columns
            return
        structural = {"div", "section", "article", "table", "ul", "ol", "li", "dl", "dt", "dd", "p", "pre", "h1", "h2", "h3", "h4", "h5", "figure", "img"}
        if not any(child.name in structural for child in node.find_all(recursive=False)):
            emit(node.get_text("\n", strip=True), {"element_path": css})
            return
        counts = {}
        for index, child in enumerate(node.children):
            if isinstance(child, Tag):
                counts[child.name] = counts.get(child.name, 0) + 1
                walk(child, f"{css} > {child.name}:nth-of-type({counts[child.name]})")
            else:
                walk(child, f"{css}::text({index})")
    walk(root, locator["selector"])
    return blocks


def _pdf_blocks(path: Path, unit: dict) -> list[dict]:
    import pdfplumber
    locator = unit["locator"]
    with pdfplumber.open(path) as document:
        page = document.pages[locator["physical_page"] - 1]
        side = locator["side"]
        bbox = (page.width / 2 if side == "right" else 0, 0, page.width / 2 if side == "left" else page.width, page.height)
        crop = page.crop(bbox)
        base = {**locator, "page_width": page.width, "page_height": page.height}
        blocks = []
        tables = crop.find_tables()
        for table_index, table in enumerate(tables):
            values = table.extract()
            xs = sorted({x for cell in table.cells for x in (cell[0], cell[2])})
            ys = sorted({y for cell in table.cells for y in (cell[1], cell[3])})
            for row_index, row in enumerate(table.rows):
                for column, cell in enumerate(row.cells):
                    if cell is None or not values[row_index][column]:
                        continue
                    span = {"rows": ys.index(cell[3]) - ys.index(cell[1]), "columns": xs.index(cell[2]) - xs.index(cell[0])}
                    blocks.append({"text": values[row_index][column], "locator": {**base, "bbox": list(cell), "table": table_index, "row": row_index, "column": column, "merged_span": span}})
        def outside_tables(obj):
            if obj.get("object_type") != "char":
                return True
            x = (obj["x0"] + obj["x1"]) / 2
            y = (obj["top"] + obj["bottom"]) / 2
            return not any(t.bbox[0] <= x <= t.bbox[2] and t.bbox[1] <= y <= t.bbox[3] for t in tables)
        for line in crop.filter(outside_tables).extract_text_lines(return_chars=False):
            blocks.append({"text": line["text"], "locator": {**base, "bbox": [line[key] for key in ("x0", "top", "x1", "bottom")]}})
        blocks.sort(key=lambda b: (b["locator"]["bbox"][1], b["locator"]["bbox"][0]))
        return blocks


def parse_unit(path: Path, format: str, unit: dict) -> list[dict]:
    if format in {'json', 'xlsx'}:
        from .structured_tables import parse
        blocks = parse(path, format, unit.get('scope', {}))
        for n, block in enumerate(blocks):
            block['locator']['block_order'] = n
        return blocks
    if format == "pdf":
        blocks = _pdf_blocks(path, unit)
    elif format == "html":
        blocks = _html_blocks(path, unit)
    elif format == "csv":
        scope = unit.get("scope", {})
        codes = set(scope.get("knowledge_input_complex_codes", []))
        column = scope.get("code_column", unit.get("code_column", "단지코드"))
        blocks, found = [], set()
        for number, row in _csv_rows(path, scope.get("encoding", "utf-8-sig")):
            if codes and column not in row:
                raise ValueError(f"CSV 코드 열 없음: {column}")
            if "physical_row" in unit["locator"] and number != unit["locator"]["physical_row"]:
                continue  # Existing row checkpoints remain readable.
            code = row.get(column)
            if not codes or code in codes:
                found.add(code)
                blocks.append({"text": "\n".join(f"{key}: {value}" for key, value in row.items()),
                               "locator": {**unit["locator"], "physical_row": number,
                                           "column_names": list(row), "official_code": code}})
        if codes - found:
            raise ValueError(f"CSV 선택 코드 누락: {sorted(codes - found)}")
    elif format in {"txt", "md"}:
        blocks = list(_text_blocks(path, format))
    elif format == "hwpx":
        all_blocks = _hwpx_blocks(path)
        if "paragraphs" in unit:
            wanted = {(loc["member"], loc["element_preorder_index_zero_based"]) for loc in unit["paragraphs"]}
            blocks = [b for b in all_blocks if (b["locator"]["member"], b["locator"]["element_preorder_index_zero_based"]) in wanted]
            if len(blocks) != len(wanted):
                raise ValueError("HWPX 선택 문단 누락")
            for block in blocks:
                block["locator"]["section"] = unit["locator"]["section"]
        else:
            blocks = [b for b in all_blocks if b["locator"]["member"] == unit["locator"]["member"]]
    else:
        raise ValueError(f"지원하지 않는 형식: {format}")
    if not blocks or not any(b["text"].strip() for b in blocks):
        raise ValueError("추출 텍스트 없음: 스캔/OCR 미지원 또는 선택 범위 손실을 확인하세요")
    for index, block in enumerate(blocks):
        block["locator"]["block_order"] = index
    return blocks

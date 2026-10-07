"""Local tabular rows with original addresses; XLSX needs only the standard library."""
import json
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def xlsx_rows(path, sheet):
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        selected = next((s for s in workbook.find('s:sheets', NS) if s.attrib['name'] == sheet), None)
        if selected is None:
            raise ValueError('XLSX sheet not found')
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        rid = selected.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        target = next(r.attrib['Target'] for r in relationships if r.attrib['Id'] == rid)
        member = target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl') / target)
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in s.iterfind('.//s:t', NS))
                       for s in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        with archive.open(member) as stream:
            for event, row in ET.iterparse(stream, events=['end']):
                if row.tag != '{' + NS['s'] + '}row':
                    continue
                values = {}
                for cell in row:
                    address = cell.attrib['r']
                    column = ''.join(c for c in address if c.isalpha())
                    value = cell.find('s:v', NS)
                    text = value.text if value is not None else ''
                    kind = cell.attrib.get('t')
                    if kind == 's': text = strings[int(text)]
                    elif kind == 'inlineStr': text = ''.join(t.text or '' for t in cell.iterfind('.//s:t', NS))
                    elif text and kind not in {'str', 'e', 'b'}:
                        number = float(text); text = int(number) if number.is_integer() else number
                    values[column] = text
                yield int(row.attrib['r']), values
                row.clear()


def parse(path, format, scope):
    equals = scope.get('equals', {})
    if format == 'xlsx':
        sheet = scope.get('sheet')
        if not sheet:
            raise ValueError('XLSX requires an explicit sheet')
        rows = iter(xlsx_rows(path, sheet))
        header_row, header = next(rows)
        if len(set(header.values())) != len(header):
            raise ValueError('Duplicate column headers')
        records = ((n, {str(header[k]): v for k, v in values.items() if k in header},
                    dict(format=format, sheet=sheet, physical_row=n, header_row=header_row,
                         cells={str(header[k]): k + str(n) for k in values if k in header})) for n, values in rows)
    else:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value, list):
            raise ValueError('JSON table must be an array')
        columns = scope.get('columns')
        records = []
        for n, row in enumerate(value):
            if isinstance(row, list):
                if not columns or len(row) != len(columns):
                    raise ValueError('Array rows require matching explicit column names')
                row = dict(zip(columns, row))
            if not isinstance(row, dict):
                raise ValueError('JSON row must be an object')
            records.append((n, row, dict(format='json', json_pointer='/' + str(n))))
    result = []
    for _, fields, locator in records:
        if any(str(fields.get(k)) != str(v) for k, v in equals.items()):
            continue
        result.append(dict(text=json.dumps(fields, ensure_ascii=False), locator=dict(locator, fields=fields)))
    if not result:
        raise ValueError('Selected table contains no rows')
    return result

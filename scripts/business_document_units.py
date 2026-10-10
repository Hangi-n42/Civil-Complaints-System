"""Research-only exact units at existing blocks and explicit HTML note boundaries."""
import re


def locate(soup, path):
    text_node = re.fullmatch(r'(.*)::text\((\d+)\)', path)
    selector = text_node[1] if text_node else path
    nodes = soup.select(selector)
    if len(nodes) != 1:
        raise ValueError('nonunique_dom_locator')
    return list(nodes[0].children)[int(text_node[2])] if text_node else nodes[0]


def units(node, text, locator):
    from bs4 import NavigableString
    if isinstance(node, NavigableString):
        if str(node) != text:
            raise ValueError('text_node_mismatch')
        return [dict(span=[0, len(text)], text=text, boundary=dict(kind='stored_block', locator=locator))]
    strings = [(s, str(s).strip()) for s in node.strings if str(s).strip()]
    if '\n'.join(value for _, value in strings) != text:
        raise ValueError('stored_projection_mismatch')
    starts, cursor = {}, 0
    for original, value in strings:
        starts[id(original)] = cursor
        cursor += len(value) + 1
    cuts = {0: dict(kind='stored_block', locator=locator)}
    for span in node.find_all('span', recursive=False):
        previous = span.previous_sibling
        while isinstance(previous, NavigableString) and not str(previous).strip():
            previous = previous.previous_sibling
        # A BR and a separately marked note are physical evidence, not a scope rule.
        if getattr(previous, 'name', None) != 'br' or not span.get_text().lstrip().startswith('※'):
            continue
        first = next((s for s in span.strings if str(s).strip()), None)
        if first is None:
            raise ValueError('empty_note')
        index = next(i for i, child in enumerate(node.find_all('span', recursive=False), 1) if child is span)
        cuts[starts[id(first)]] = dict(kind='br_note_span', locator=locator + f' > span:nth-of-type({index})')
    positions = sorted(cuts) + [len(text)]
    result = [dict(span=[start, end], text=text[start:end], boundary=cuts[start])
              for start, end in zip(positions, positions[1:])]
    assert ''.join(u['text'] for u in result) == text
    return result


def selfcheck():
    from bs4 import BeautifulSoup
    node = BeautifulSoup('<li>앞(안)<br/><span>※ 뒤</span></li>', 'html.parser').li
    result = units(node, '앞(안)\n※ 뒤', '#x')
    assert [r['span'] for r in result] == [[0, 5], [5, 8]]
    for html, text in [('<li>앞\n뒤</li>', '앞\n뒤'), ('<li>앞(안)</li>', '앞(안)'),
                       ('<li>앞<br/>뒤</li>', '앞\n뒤'), ('<li>앞<span>※ 뒤</span></li>', '앞\n※ 뒤')]:
        assert len(units(BeautifulSoup(html, 'html.parser').li, text, '#x')) == 1
    repeated = BeautifulSoup('<li>※ 뒤<br/><span>※ 뒤</span></li>', 'html.parser').li
    assert units(repeated, '※ 뒤\n※ 뒤', '#x')[1]['span'] == [4, 7]
    try:
        units(node, '앞(다름)\n※ 뒤', '#x')
    except ValueError:
        pass
    else:
        raise AssertionError('changed original accepted')
    print('DOM note boundary, no newline/parenthesis rule, repeated text and projection mismatch checks passed')


if __name__ == '__main__':
    selfcheck()

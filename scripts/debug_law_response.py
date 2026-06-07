"""법제처 lawService 응답 구조 진단기 (로컬, 1회용).

자치법규(target=ordin) 본문이 0조문으로 나오는 원인을 잡기 위해, 실제 응답의
키 구조를 덤프하고 parse_law_body 가 무엇을 찾는지 보여준다.

사용:
  export LEGISLATION_API_KEY=your_id
  python scripts/debug_law_response.py --id 2160706 --target ordin
  # 법령과 비교하려면: python scripts/debug_law_response.py --id 001823 --target law

출력의 'key-tree' 와 '0조문 여부' 를 그대로 공유하면 파서를 정확히 맞출 수 있다.
원본 JSON 은 data/laws/_debug_<target>_<id>.json 으로 저장된다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.structuring.law_corpus import parse_law_body, _find_article_units  # noqa: E402

BASE = "http://www.law.go.kr/DRF/lawService.do"


def key_tree(node, depth=0, max_depth=4, max_items=6):
    pad = "  " * depth
    if depth > max_depth:
        return f"{pad}…"
    lines = []
    if isinstance(node, dict):
        for k, v in list(node.items())[:20]:
            vt = type(v).__name__
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k} ({vt})")
                lines.append(key_tree(v, depth + 1, max_depth, max_items))
            else:
                sval = str(v).replace("\n", " ")[:40]
                lines.append(f"{pad}{k}: {sval!r}")
    elif isinstance(node, list):
        lines.append(f"{pad}[len={len(node)}]")
        if node:
            lines.append(key_tree(node[0], depth + 1, max_depth, max_items))
    return "\n".join(x for x in lines if x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oc", default=os.getenv("LEGISLATION_API_KEY", ""))
    ap.add_argument("--id", required=True)
    ap.add_argument("--target", default="ordin")
    ap.add_argument("--idparam", default="ID", help="ID 파라미터명 (ID 또는 MST 시도)")
    args = ap.parse_args()
    if not args.oc:
        raise SystemExit("OC 키 필요: --oc 또는 LEGISLATION_API_KEY")

    params = {"OC": args.oc, "target": args.target, "type": "JSON", args.idparam: args.id}
    url = f"{BASE}?{urllib.parse.urlencode(params, encoding='utf-8')}"
    print("요청:", url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")

    out_path = ROOT / "data" / "laws" / f"_debug_{args.target}_{args.id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(raw, encoding="utf-8")
    print("원본 저장:", out_path, f"({len(raw)} chars)")
    print("응답 앞부분:", raw[:200].replace("\n", " "))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"\n[결과] JSON 아님(HTML/에러 가능): {e}")
        return

    print("\n=== KEY TREE (depth≤4) ===")
    print(key_tree(data))

    units = _find_article_units(data)
    recs = parse_law_body({"law_id": args.id, "name": "DEBUG", "doc_type": args.target}, data)
    print(f"\n[결과] _find_article_units 발견 단위: {len(units)} / parse_law_body 조문: {len(recs)}")
    if units[:1]:
        print("첫 단위 키:", list(units[0].keys()))


if __name__ == "__main__":
    main()

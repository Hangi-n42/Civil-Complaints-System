"""법령 사전 빌더 (legal_refs 고도화 Phase A) — 로컬 실행용.

법제처 국가법령정보 공동활용 OPEN API 로 현행법령 '목록'과 부산 자치법규 목록을
받아 사전 JSON 을 만든다. 본문(조문)은 받지 않는다(그건 Phase B).

  - 현행법령 목록  : lawSearch.do?target=law   → law_dictionary.json
  - 부산 자치법규  : lawSearch.do?target=ordin  → busan_ordinances.json

인증: OC 파라미터 = 법제처에 등록한 이메일의 ID(@ 앞부분) 또는 이메일.
  $ export LEGISLATION_API_KEY=your_id        # 또는 --oc 인자
  $ python scripts/build_law_dictionary.py

주의:
  - 이 스크립트는 외부 API 를 호출하므로 네트워크가 되는 로컬에서 실행한다.
  - 응답 필드명은 법제처 lawSearch(target=law) 규격을 따른다. 최초 1회는
    아래 SAMPLE_URL 을 브라우저로 열어 실제 필드명을 확인 후 필요시 KEY_MAP 조정.
    SAMPLE: http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=JSON&display=2&query=건축법
  - 무료 서비스이므로 과도한 요청은 피한다(페이지 간 짧은 sleep 포함).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://www.law.go.kr/DRF/lawSearch.do"
DISPLAY = 100  # 페이지당 최대 100

# 응답 키 후보(법제처 규격 우선, 변형 대비 다중 후보).
KEY_MAP = {
    "name": ["법령명한글", "법령명", "자치법규명", "lawNm"],
    "abbr": ["법령약칭명", "약칭"],
    "law_id": ["법령ID", "법령일련번호", "자치법규ID", "자치법규일련번호", "id"],
    "dept": ["소관부처명", "지자체기관명", "소관부처"],
    "type": ["법령구분명", "자치법규종류"],
    "enforce_date": ["시행일자"],
    "org": ["지자체기관명", "소관부처명"],
}


def _first(item: Dict[str, Any], keys: List[str]) -> str:
    for k in keys:
        v = item.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _http_get_json(url: str) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [warn] JSON 파싱 실패 (HTML 응답 가능). URL 확인: {url}")
        return None


def _extract_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """응답 JSON 에서 항목 리스트를 찾아 반환(루트 키가 target 마다 달라 방어적 탐색)."""
    if not isinstance(data, dict):
        return []
    for root in data.values():
        if isinstance(root, dict):
            for v in root.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
            # 단건이 dict 로 올 때
        if isinstance(root, list) and root and isinstance(root[0], dict):
            return root
    return []


def fetch_all(oc: str, target: str, query: str = "") -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page = 1
    while True:
        params = {"OC": oc, "target": target, "type": "JSON", "display": DISPLAY, "page": page}
        if query:
            params["query"] = query
        url = f"{BASE}?{urllib.parse.urlencode(params, encoding='utf-8')}"
        data = _http_get_json(url)
        if not data:
            break
        batch = _extract_items(data)
        if not batch:
            break
        items.extend(batch)
        print(f"  target={target} page={page} +{len(batch)} (누적 {len(items)})")
        if len(batch) < DISPLAY:
            break
        page += 1
        time.sleep(0.3)  # 과도요청 방지
    return items


def to_law_record(item: Dict[str, Any]) -> Dict[str, str]:
    return {
        "name": _first(item, KEY_MAP["name"]),
        "abbr": _first(item, KEY_MAP["abbr"]),
        "law_id": _first(item, KEY_MAP["law_id"]),
        "dept": _first(item, KEY_MAP["dept"]),
        "type": _first(item, KEY_MAP["type"]),
        "enforce_date": _first(item, KEY_MAP["enforce_date"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oc", default=os.getenv("LEGISLATION_API_KEY", ""),
                    help="법제처 OC 키(이메일 ID). 미지정 시 env LEGISLATION_API_KEY")
    ap.add_argument("--busan-keyword", default="부산", help="자치법규 부산 필터 키워드")
    args = ap.parse_args()
    if not args.oc:
        raise SystemExit("OC 키가 필요합니다. --oc 또는 LEGISLATION_API_KEY 를 설정하세요.")

    # 1) 현행법령 목록
    print("[1/2] 현행법령 목록 수집 (target=law)")
    laws_raw = fetch_all(args.oc, "law")
    laws = [r for r in (to_law_record(x) for x in laws_raw) if r["name"]]
    # 이름 기준 중복 제거(최신 시행일 우선)
    dedup: Dict[str, Dict[str, str]] = {}
    for r in laws:
        cur = dedup.get(r["name"])
        if cur is None or r["enforce_date"] > cur["enforce_date"]:
            dedup[r["name"]] = r
    law_list = list(dedup.values())
    (ROOT / "data" / "laws").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "laws" / "law_dictionary.json").write_text(
        json.dumps(law_list, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> law_dictionary.json ({len(law_list)} 법령)")

    # 2) 부산 자치법규 (query=부산 + 기관명 부산 필터)
    print("[2/2] 부산 자치법규 수집 (target=ordin)")
    ordin_raw = fetch_all(args.oc, "ordin", query=args.busan_keyword)
    kw = args.busan_keyword
    ordin = []
    for x in ordin_raw:
        rec = to_law_record(x)
        org = _first(x, KEY_MAP["org"])
        if not rec["name"]:
            continue
        if kw in rec["name"] or kw in org:  # 부산 소속만
            ordin.append(rec)
    (ROOT / "data" / "laws" / "busan_ordinances.json").write_text(
        json.dumps(ordin, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> busan_ordinances.json ({len(ordin)} 자치법규)")
    print("\n완료. app/structuring/legal_dictionary.py 가 두 파일을 자동 사용합니다.")


if __name__ == "__main__":
    main()

"""조문 코퍼스 빌더 (Phase B) — 로컬 실행용.

법제처 lawService.do(본문)로 '핵심 법령 + 부산 본청 자치법규'의 조문을 받아
data/laws/law_articles.json (조 단위 레코드의 JSON 배열) 을 만든다. 인덱싱은 LawArticleStore.

대상(화이트리스트) 기본값:
  - 핵심 국가법령: enrichment.LEGAL_REF_LEXICON 의 법령명 → law_dictionary.json 으로 law_id 해석
  - 부산 본청 자치법규: busan_ordinances.json 중 dept == '부산광역시'
  (--laws 로 법령명/ID 추가, --all-ordinances 로 부산 전체 구·군 포함)

인증: OC = 법제처 등록 이메일 ID.
  $ export LEGISLATION_API_KEY=your_id
  $ python scripts/build_law_corpus.py

주의:
  - 외부 API 호출 → 네트워크 되는 로컬에서 실행. 무료지만 과도요청 금지(sleep 포함).
  - 본문 응답 스키마는 app/structuring/law_corpus.py 의 parse_law_body 가 방어적으로 처리
    (컨테이너 키 비의존 재귀 조문 탐색). 그래도 0조문이 다수면 SAMPLE 로 구조 확인.
    SAMPLE(법령):   http://www.law.go.kr/DRF/lawService.do?OC=test&target=law&type=JSON&ID=001823
    SAMPLE(자치법규): http://www.law.go.kr/DRF/lawService.do?OC=test&target=ordin&type=JSON&ID=<자치법규ID>
  - 이미 수집한 law_id 는 건너뛴다(재개 가능). --rebuild 로 새로.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.structuring.enrichment import LEGAL_REF_LEXICON  # noqa: E402
from app.structuring.law_corpus import parse_law_body      # noqa: E402

BASE = "http://www.law.go.kr/DRF/lawService.do"
LAWS_DIR = ROOT / "data" / "laws"
OUT = LAWS_DIR / "law_articles.json"
LAW_DICT = LAWS_DIR / "law_dictionary.json"
ORDIN_DICT = LAWS_DIR / "busan_ordinances.json"


def _http_get_json(url: str) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] 수신/파싱 실패: {exc} ({url})")
        return None


def _service_url(target: str, law_id: str, fmt: str = "JSON") -> str:
    params = {"OC": OC, "target": target, "type": fmt, "ID": law_id}
    return f"{BASE}?{urllib.parse.urlencode(params, encoding='utf-8')}"


def select_targets(args) -> List[Dict[str, str]]:
    """수집 대상 [{law_id, name, target, doc_type, dept, enforce_date}] 구성."""
    # 가운뎃점 변형( · U+00B7 vs ㆍ U+318D)·공백 차이를 흡수해 이름을 정규화한다.
    def _norm(s: str) -> str:
        return s.replace("ㆍ", "").replace("·", "").replace("‧", "").replace(" ", "")
    raw = json.loads(LAW_DICT.read_text(encoding="utf-8"))
    laws = {_norm(x["name"]): x for x in raw}
    targets: List[Dict[str, str]] = []

    # 1) 핵심 국가법령 (lexicon + --laws)
    wanted = set(LEGAL_REF_LEXICON.keys()) | set(args.laws or [])
    for name in wanted:
        rec = laws.get(_norm(name))
        if not rec:
            print(f"  [skip] 사전에 없는 법령명: {name}")
            continue
        targets.append({"law_id": rec["law_id"], "name": rec["name"], "target": "law",
                        "doc_type": "law", "dept": rec.get("dept", ""),
                        "enforce_date": rec.get("enforce_date", "")})

    # 2) 부산 자치법규
    if ORDIN_DICT.exists():
        ordn = json.loads(ORDIN_DICT.read_text(encoding="utf-8"))
        for rec in ordn:
            if not args.all_ordinances and rec.get("dept") != "부산광역시":
                continue
            targets.append({"law_id": rec["law_id"], "name": rec["name"], "target": "ordin",
                            "doc_type": "ordinance", "dept": rec.get("dept", ""),
                            "enforce_date": rec.get("enforce_date", "")})
    return targets


def main() -> None:
    global OC
    ap = argparse.ArgumentParser()
    ap.add_argument("--oc", default=os.getenv("LEGISLATION_API_KEY", ""))
    ap.add_argument("--laws", nargs="*", default=[], help="추가 국가법령명")
    ap.add_argument("--all-ordinances", action="store_true", help="부산 구·군 조례까지 전체")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    OC = args.oc
    if not OC:
        raise SystemExit("OC 키가 필요합니다. --oc 또는 LEGISLATION_API_KEY 설정.")

    LAWS_DIR.mkdir(parents=True, exist_ok=True)
    # 기존 JSON 배열을 읽어 재개(이미 수집한 law_id 는 건너뜀)
    all_records: List[Dict[str, Any]] = []
    done_ids: set = set()
    if OUT.exists() and not args.rebuild:
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
            if isinstance(prev, list):
                all_records = prev
                done_ids = {r.get("law_id") for r in prev}
        except Exception:
            pass

    targets = select_targets(args)
    print(f"대상 법령/자치법규: {len(targets)} (이미 수집 {len(done_ids)})")

    new_articles = 0
    zero_hits: List[str] = []
    for i, t in enumerate(targets, 1):
        if t["law_id"] in done_ids:
            continue
        data = _http_get_json(_service_url(t["target"], t["law_id"]))
        if not data:
            continue
        html_url = _service_url(t["target"], t["law_id"], fmt="HTML")
        records = parse_law_body(t, data, source_url=html_url)
        if not records:
            zero_hits.append(f"{t['name']} (target={t['target']}, ID={t['law_id']})")
        all_records.extend(records)
        new_articles += len(records)
        print(f"  [{i}/{len(targets)}] {t['name']} → {len(records)} 조문")
        time.sleep(0.3)  # 과도요청 방지

    OUT.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료: +{new_articles} 조문 (누적 {len(all_records)}) → {OUT}")
    if zero_hits:
        # 0조문은 보통 본문 응답 스키마가 파서 가정과 다를 때 발생한다.
        print(f"\n[진단] 0조문 {len(zero_hits)}건. 본문 스키마 확인이 필요할 수 있음. 예:")
        for z in zero_hits[:3]:
            print(f"   - {z}")
        print("   SAMPLE 응답을 열어 조문 구조를 확인하세요(빌더 상단 주석 SAMPLE URL).")
    print("인덱싱: python -c \"from app.retrieval.law_article_store import get_law_article_store as g; print(g().build_index(rebuild=True))\"")


if __name__ == "__main__":
    main()

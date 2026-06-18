"""데모 민원(pending_cases_8.json)에 responsible_unit(담당부서 추천)을 백필한다.

DepartmentAssigner.assign()을 케이스별로 호출해 structured.responsible_unit에 채운다.
질의 구성은 구조화 서비스의 _derive_responsible_unit과 동일하게 build_query_text 사용.
데모 데이터 준비용 1회성 스크립트(워크벤치에서 실제 추천을 표시하기 위함).

실행:
  ENABLE_RESPONSIBLE_UNIT=true python scripts/backfill_demo_responsible_unit.py
  (assign()은 플래그와 무관하게 직접 동작하지만, 의도를 명시하기 위해 켜고 실행)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.structuring.department_assigner import build_query_text, get_department_assigner

DEMO_PATH = ROOT / "data" / "demo" / "pending_cases_8.json"


def _case_query(case: dict) -> str:
    structured = case.get("structured") or {}
    raw_text = str(case.get("raw_text") or case.get("text") or "")
    entities = structured.get("entities") or []
    entity_texts = [str(e.get("text", "")) for e in entities if isinstance(e, dict) and e.get("text")]
    key_terms = structured.get("key_terms") or []
    return build_query_text(raw_text=raw_text, entity_texts=entity_texts, key_terms=key_terms)


def main() -> None:
    cases = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    assigner = get_department_assigner()

    for case in cases:
        query = _case_query(case)
        units = assigner.assign(query, use_llm=False)
        case.setdefault("structured", {})["responsible_unit"] = units
        top = f"{units[0]['name']} (conf={units[0]['confidence']})" if units else "(추천 없음)"
        print(f"{case.get('case_id')}: {top} · 후보 {len(units)}")

    DEMO_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n백필 완료 → {DEMO_PATH}")


if __name__ == "__main__":
    main()

"""FE #388 테스트용 QA 응답 픽스처 생성기.

실제 데모 민원(data/demo/pending_cases_8.json)에 백엔드의 실제 세그먼트 분해 규칙
(app.api.routers.generation._derive_request_segments)을 그대로 적용해 단일/복합/빈
segment QA 응답 픽스처를 만든다. LLM·서버 없이 결정론적으로 재생성 가능하다.

`answer`는 분석 메타데이터가 섞이지 않은 순수 회신문 본문(대표값)이다 — 이슈 검증의
핵심은 answer의 "내용"이 아니라 "복합 케이스에서도 textarea에는 answer만 노출되는가"이므로
대표 회신문으로 충분하다.

재생성:
    python frontend/__tests__/fixtures/build_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# frontend/__tests__/fixtures -> repo root
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.api.routers.generation import _derive_request_segments  # noqa: E402

DEMO = ROOT / "data" / "demo" / "pending_cases_8.json"
OUT = Path(__file__).resolve().parent / "qa_demo_fixtures.json"


def _request_text(case: dict) -> str:
    structured = case.get("structured") or {}
    request = (structured.get("request") or {}).get("text")
    return request or case.get("raw_text") or ""


def _summary_text(case: dict) -> str:
    structured = case.get("structured") or {}
    result = (structured.get("result") or {}).get("text")
    observation = (structured.get("observation") or {}).get("text")
    return result or observation or ""


def _answer(case: dict) -> str:
    """메타데이터가 섞이지 않은 순수 회신문 본문(대표값)."""
    title = case.get("title") or "민원"
    request = _request_text(case)
    return (
        f"안녕하세요. 접수하신 '{title}' 민원에 대해 안내드립니다.\n"
        f"요청하신 사항({request})을 관련 부서에서 확인하였으며, 처리 가능 여부와 "
        f"일정은 검토 후 신속히 회신드리겠습니다.\n"
        f"추가 문의 사항은 담당 부서로 연락 주시기 바랍니다."
    )


def _action_items(segments: list[str]) -> list[str]:
    return [f"{seg[:40].strip()} 관련 확인 및 안내" for seg in segments]


def _build_case(case: dict) -> dict:
    segments = _derive_request_segments(_request_text(case))
    mode = "multi" if len(segments) >= 2 else "single" if len(segments) == 1 else "empty"
    return {
        "complaintId": case["case_id"],
        "title": case.get("title"),
        "answer": _answer(case),
        "structuredOutput": {
            "summary": _summary_text(case),
            "actionItems": _action_items(segments),
            "requestSegments": segments,
        },
        "_meta": {"n_segments": len(segments), "mode": mode},
    }


def main() -> None:
    demo_cases = json.loads(DEMO.read_text(encoding="utf-8"))
    cases = [_build_case(case) for case in demo_cases]

    # 빈 segment 경계 케이스(합성): 빈 query는 백엔드 규칙상 빈 세그먼트를 만든다.
    empty_case = {
        "complaintId": "NEW-EMPTY",
        "title": "빈 세그먼트 경계 케이스",
        "answer": "안녕하세요. 접수하신 민원을 확인 후 안내드리겠습니다.",
        "structuredOutput": {
            "summary": "",
            "actionItems": [],
            "requestSegments": _derive_request_segments(""),
        },
        "_meta": {"n_segments": len(_derive_request_segments("")), "mode": "empty"},
    }

    payload = {
        "source": "data/demo/pending_cases_8.json + app.api.routers.generation._derive_request_segments",
        "note": "FE #388 단위 테스트 픽스처. `python frontend/__tests__/fixtures/build_fixtures.py`로 재생성.",
        "cases": cases,
        "empty": empty_case,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    multi = sum(1 for c in cases if c["_meta"]["mode"] == "multi")
    single = sum(1 for c in cases if c["_meta"]["mode"] == "single")
    print(f"wrote {OUT.relative_to(ROOT)} | cases={len(cases)} (multi={multi}, single={single}) + 1 empty")


if __name__ == "__main__":
    main()

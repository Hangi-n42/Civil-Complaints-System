"""버전 중립(version-neutral) 평가 쿼리셋 생성기.

검색 평가셋의 쿼리는 v1 시대 구조화 파이프라인(관찰/결과/요청/맥락 4요소)으로
생성되어, 같은 구조화를 거친 civil_cases_v1 컬렉션에 유리한 home-field 편향이 있다.
이 스크립트는 동일한 query_id / source_id 를 유지하되, 쿼리 텍스트를 어느 컬렉션
버전의 구조화도 거치지 않은 "민원인 원문"(civil_text = 제목 + 민원인 질문, 상담사
답변·4요소 구조화 제외)으로 교체해, 컬렉션 버전(v1/v3) 간 공정 비교를 가능하게 한다.

원문 미포함(원천 데이터는 출력하지 않으며, 평가용 쿼리 텍스트만 생성한다).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.structuring.preprocessing import _prepared_record, civil_text

DEFAULT_SRC_DIR = PROJECT_ROOT / "data" / "Public_Civil_Service_LLM_Data"
DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "data" / "evaluation" / "version_neutral" / "queries.jsonl"

# v1 구조화본 식별용 4요소 마커. 중립 쿼리에는 절대 포함되면 안 된다.
STRUCT_MARKERS = ("관찰:", "결과:", "요청:", "맥락:")


def build_source_map(src_dir: Path) -> dict[str, dict[str, Any]]:
    """원천 데이터(*.json)를 스캔해 source_id -> 원천 레코드 매핑을 만든다."""
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(Path(src_dir).rglob("*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 손상 파일은 건너뛴다
            continue
        for item in data if isinstance(data, list) else [data]:
            sid = str(item.get("source_id") or "")
            if sid and sid not in out:
                out[sid] = item
    return out


def load_eval_queries(path: Path) -> list[dict[str, Any]]:
    """기존 평가셋 queries.jsonl 로드 (query_id / source_id 보존)."""
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def build_neutral_queries(
    queries: list[dict[str, Any]],
    source_map: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], list[str]]:
    """기존 쿼리 목록을 받아 중립 쿼리 행 / 누락 / 구조화마커 검출 목록을 돌려준다.

    누락(원문 없음·빈 본문)은 폴백으로 원 쿼리를 끼워넣지 않고 명시적으로 보고한다
    (폴백을 쓰면 중립성이 깨지기 때문).
    """
    rows: list[dict[str, Any]] = []
    missing: list[tuple[str, str]] = []
    marker_hit: list[str] = []

    for q in queries:
        qid = str(q.get("query_id") or q.get("_id") or "")
        sid = str(q.get("source_id") or "")
        raw = source_map.get(sid)
        if not raw:
            missing.append((qid, sid))
            continue
        text = civil_text(_prepared_record(raw)).strip()
        if not text:
            missing.append((qid, sid))
            continue
        if any(marker in text for marker in STRUCT_MARKERS):
            marker_hit.append(qid)
        rows.append(
            {
                "query_id": qid,
                "query": text,
                "source_id": sid,
                "source": q.get("source", ""),
                "category": q.get("category", ""),
                "query_type": "raw_citizen_text",
            }
        )
    return rows, missing, marker_hit


def main() -> int:
    parser = argparse.ArgumentParser(description="버전 중립 평가 쿼리셋 생성")
    parser.add_argument("--queries", default=str(DEFAULT_QUERIES), help="기존 평가셋 queries.jsonl")
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC_DIR), help="원천 데이터 디렉터리")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="출력 queries.jsonl 경로")
    args = parser.parse_args()

    queries = load_eval_queries(Path(args.queries))
    source_map = build_source_map(Path(args.src_dir))
    rows, missing, marker_hit = build_neutral_queries(queries, source_map)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[build-vn] 원천 레코드 {len(source_map)} | 입력 쿼리 {len(queries)} → 생성 {len(rows)}")
    print(f"[build-vn] 누락 {len(missing)} | 구조화마커 검출 {len(marker_hit)}")
    if missing:
        print("  누락(query_id, source_id):", missing[:20])
    if marker_hit:
        print("  구조화마커 검출(query_id):", marker_hit[:20])
    print(f"[write] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

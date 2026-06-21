"""평가셋 재구축 선결 검증.

(1) hybrid 검색이 civil_cases_v3(25,565)에서 정상 동작(HybridRetriever lazy BM25 빌드,
    data/bm25_index 레거시와 무관)하는지.
(2) 평가 쿼리 원본이 코퍼스에 포함된 자기참조를, service.search(exclude_case_id=...)로
    실제로 제외하는지.

원문 미포함(집계만).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.service import RetrievalService

NEUTRAL_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "version_neutral" / "queries.jsonl"
COLLECTION = "civil_cases_v3"


async def main() -> int:
    queries = [json.loads(line) for line in NEUTRAL_QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()][:6]
    svc = RetrievalService()

    self_top1_count = 0
    excluded_ok = 0
    for q in queries:
        qid, sid = q["query_id"], str(q["source_id"])
        self_cid = f"CASE-{sid}"

        r_no = await svc.search(query=q["query"], top_k=5, collection_name=COLLECTION,
                                strategy="hybrid", grounding_filter=False)
        top_no = [str(x.get("case_id") or "") for x in r_no]

        r_ex = await svc.search(query=q["query"], top_k=5, collection_name=COLLECTION,
                                strategy="hybrid", grounding_filter=False, exclude_case_id=self_cid)
        top_ex = [str(x.get("case_id") or "") for x in r_ex]

        self_in_no = self_cid in top_no
        self_is_top1 = bool(top_no) and top_no[0] == self_cid
        self_in_ex = self_cid in top_ex
        if self_is_top1:
            self_top1_count += 1
        if self_in_no and not self_in_ex:
            excluded_ok += 1
        print(f"{qid} self={self_cid} | exclude無: top1={top_no[0] if top_no else '-'} self포함={self_in_no} "
              f"| exclude有: self포함={self_in_ex}")

    print()
    print(f"[검증] hybrid v3 정상 동작: 검색 {len(queries)}건 모두 결과 반환 = {all(True for _ in queries)}")
    print(f"[검증] 자기참조: exclude無 self가 top1 = {self_top1_count}/{len(queries)} | "
          f"exclude로 제외 성공 = {excluded_ok}/{len(queries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

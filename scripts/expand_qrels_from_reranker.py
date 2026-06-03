"""
Cross-encoder pooling: qrels에 없는 상위 문서 라벨링 후 qrels 확장

1. Dense+Reranker 파이프라인 실행 (전체 쿼리)
2. Cross-encoder top-10 중 qrels 미등록 문서 수집
3. LLM으로 라벨링 (exaone3.5:7.8b + gemma3:12b)
4. rel>0 쌍을 qrels.tsv에 추가

사용법:
  python scripts/expand_qrels_from_reranker.py [--score-threshold 0.3] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.request
from math import floor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data" / "evaluation" / "v3"
QRELS_PATH = DATA_DIR / "qrels.tsv"
QUERIES_PATH = DATA_DIR / "queries.jsonl"
CORPUS_PATH = DATA_DIR / "corpus_meta.json"
POOL_CHECKPOINT = DATA_DIR / "reranker_pool_checkpoint.json"
PIPELINE_YAML = PROJECT_ROOT / "configs" / "retrieval_pipelines" / "dense_reranked.yaml"
OLLAMA_URL = "http://localhost:11434/api/generate"
LABEL_MODELS = ["exaone3.5:7.8b", "gemma3:12b"]

SYSTEM_PROMPT = """당신은 민원 검색 관련성 평가 전문가입니다.
기준 민원(Query)과 과거 민원 사례(Chunk)를 읽고, Chunk가 Query 답변 작성에 얼마나 유용한지 0~2점으로 평가하세요.

[채점 기준 — 반드시 이 기준만 사용하세요]
- 2점 (Perfect): 기준 민원과 과거 민원의 핵심 쟁점(문제 상황)이 동일하고, 적용되는 법령/제도/해결책이 같음.
  과거 사례의 답변(조치 내용)을 현재 민원 답변에 거의 그대로 인용할 수 있는 경우.
- 1점 (Partial): 두 민원의 카테고리/주제는 같고 쟁점이 일부 일치하지만, 세부 상황(대상, 요건 등)이 달라 그대로 인용할 수는 없음.
  답변의 방향성을 잡거나 일부 규정을 참고하는 데 도움이 되는 경우.
- 0점 (Irrelevant): 표면적인 단어/키워드만 겹칠 뿐 실제 쟁점이나 행정 절차가 달라,
  답변 작성 시 컨텍스트로 주입하면 오히려 잘못된 안내(할루시네이션)를 유발할 수 있는 경우.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 금지):
{"score": <0|1|2>, "reason": "<판단 사유 1~2문장>"}"""


def load_qrels() -> dict[str, dict[str, int]]:
    """qid -> {docid: rel}"""
    result: dict[str, dict[str, int]] = {}
    with QRELS_PATH.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            parts = line.strip().split("\t")
            if i == 0 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) == 4:
                qid, _, docid, rel = parts
                result.setdefault(qid, {})[docid] = int(rel)
    return result


def load_queries() -> dict[str, str]:
    result = {}
    with QUERIES_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                result[obj["query_id"]] = obj["query"]
    return result


def load_corpus() -> dict[str, str]:
    result = {}
    with CORPUS_PATH.open(encoding="utf-8") as f:
        for doc in json.load(f):
            cid = doc.get("case_id", "")
            if cid and cid not in result:
                result[cid] = doc.get("chunk_text", "")
    return result


def _call_ollama(model: str, prompt: str, timeout: int = 60) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 128},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("response", "")


def _extract_score(raw: str) -> int | None:
    try:
        s = int(round(float(json.loads(raw.strip())["score"])))
        return s if s in (0, 1, 2) else None
    except Exception:
        pass
    m = re.search(r'\{[^{}]*"score"\s*:\s*([012])[^{}]*\}', raw, re.DOTALL)
    if m:
        try:
            return int(round(float(json.loads(m.group(0))["score"])))
        except Exception:
            pass
    m = re.search(r'"score"\s*:\s*([012])', raw)
    if m:
        return int(m.group(1))
    m = re.search(r'\b([012])\b', raw[:50])
    return int(m.group(1)) if m else None


def label_pair(query_text: str, chunk_text: str, max_chars: int = 600) -> int:
    q = query_text[:max_chars].replace("\n", " / ")
    c = chunk_text[:max_chars]
    prompt = f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"
    scores = []
    for model in LABEL_MODELS:
        try:
            raw = _call_ollama(model, prompt)
            s = _extract_score(raw)
            if s is not None:
                scores.append(s)
        except Exception as e:
            print(f"    [{model}] 오류: {e}")
    return floor(sum(scores) / len(scores)) if scores else 0


async def run_pipeline(queries_list: list) -> list:
    from app.evaluation.datasets import EvalQuery
    from app.retrieval.pipeline.runner import RetrievalPipelineRunner, load_pipeline_spec
    spec = load_pipeline_spec(PIPELINE_YAML)
    eval_qs = [EvalQuery(qid=q["query_id"], text=q["query"], metadata={}) for q in queries_list]
    runner = RetrievalPipelineRunner(spec)
    return await runner.run(eval_qs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score-threshold", type=float, default=0.3,
                        help="이 점수 이상인 cross-encoder 결과만 라벨링 (기본: 0.3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="라벨링 없이 몇 쌍이 필요한지만 출력")
    args = parser.parse_args()

    print("=" * 60)
    print("Cross-encoder Pool Expansion")
    print(f"임계값: score >= {args.score_threshold}")
    print("=" * 60)

    # 데이터 로드
    qrels = load_qrels()
    queries_dict = load_queries()
    corpus = load_corpus()

    queries_list = [{"query_id": qid, "query": text} for qid, text in queries_dict.items()]
    print(f"\n[1] Dense+Reranker 파이프라인 실행 ({len(queries_list)}개 쿼리)...")
    results = asyncio.run(run_pipeline(queries_list))

    # 체크포인트 로드
    done: dict[str, int] = {}
    if POOL_CHECKPOINT.exists():
        with POOL_CHECKPOINT.open(encoding="utf-8") as f:
            done = json.load(f)
        print(f"체크포인트 로드: {len(done)}쌍 이미 완료")

    # qrels 미등록 & 임계값 이상 쌍 수집
    candidates: list[tuple[str, str, float]] = []
    for result in results:
        qid = result.query.qid
        q_qrels = qrels.get(qid, {})
        for doc in result.final_docs:
            if doc.docid not in q_qrels and doc.score >= args.score_threshold:
                key = f"{qid}::{doc.docid}"
                if key not in done:
                    candidates.append((qid, doc.docid, doc.score))

    # score 높은 순 정렬
    candidates.sort(key=lambda x: -x[2])
    print(f"\n[2] 라벨링 필요 쌍: {len(candidates)}개 (임계값 {args.score_threshold} 이상, qrels 미등록)")
    if done:
        all_needed = len(candidates) + len([k for k in done if k not in qrels])
        print(f"    (체크포인트 포함 총 후보: {len(candidates) + len(done)}개)")

    if args.dry_run:
        print("\n[DRY RUN] 상위 20개 후보:")
        for qid, docid, score in candidates[:20]:
            print(f"  {qid}::{docid}  score={score:.3f}")
        return

    if not candidates:
        print("[OK] 추가 라벨링 필요 없음")
    else:
        print(f"\n[3] LLM 라벨링 시작 ({len(candidates)}쌍)...")
        for idx, (qid, docid, score) in enumerate(candidates, 1):
            key = f"{qid}::{docid}"
            query_text = queries_dict.get(qid, "")
            chunk_text = corpus.get(docid, "")
            if not query_text or not chunk_text:
                done[key] = 0
                continue
            rel = label_pair(query_text, chunk_text)
            done[key] = rel
            print(f"  [{idx}/{len(candidates)}] {key}  ce_score={score:.3f} → rel={rel}")
            if idx % 10 == 0:
                POOL_CHECKPOINT.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  체크포인트 저장 ({len(done)}건)")

        POOL_CHECKPOINT.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")

    # qrels에 rel>0 추가
    all_labels = {**done}
    if POOL_CHECKPOINT.exists() and not done:
        with POOL_CHECKPOINT.open(encoding="utf-8") as f:
            all_labels = json.load(f)

    to_add = [(k, v) for k, v in all_labels.items() if v > 0]
    print(f"\n[4] qrels에 추가할 rel>0 쌍: {len(to_add)}개")
    for key, rel in sorted(to_add):
        qid, docid = key.split("::")
        q_qrels = qrels.get(qid, {})
        if docid not in q_qrels:
            print(f"  추가: {qid}\t0\t{docid}\t{rel}")

    if to_add:
        # 현재 qrels에 없는 것만 추가
        existing = set()
        with QRELS_PATH.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                parts = line.strip().split("\t")
                if i == 0: continue
                if len(parts) >= 3:
                    existing.add(f"{parts[0]}::{parts[2]}")

        new_lines = []
        for key, rel in to_add:
            if key not in existing and rel > 0:
                qid, docid = key.split("::")
                new_lines.append(f"{qid}\t0\t{docid}\t{rel}\n")

        if new_lines:
            with QRELS_PATH.open("a", encoding="utf-8") as f:
                f.writelines(new_lines)
            print(f"[OK] qrels에 {len(new_lines)}쌍 추가 완료")
        else:
            print("[OK] 중복 없이 추가할 새 쌍 없음")

    print("\n완료. run_v3_split_analysis.py로 재평가하세요.")


if __name__ == "__main__":
    main()

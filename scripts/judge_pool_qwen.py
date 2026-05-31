"""
3번째 채점관 Qwen2.5-14B로 공정 풀(5,508쌍) 채점 → 3-채점관 중앙값 집계.

ax4(약한 검증자)를 폐기하고, 유능한 3 채점관
  exaone3.5:7.8b + gemma3:12b + qwen2.5:14b
의 **중앙값(median)**으로 최종 라벨을 만든다. 세 채점관의 상호 일치도(Fleiss/Cohen κ)가
검증 지표를 겸한다 → 별도 감독자 불필요.

- 0~2 척도(relabel_new_qrels_v3.SYSTEM_PROMPT 재사용), qwen은 컨텍스트 충분 → 600자
- exaone/gemma 점수는 checkpoints/fair_pool.json 에서 재사용 (재채점 안 함)
- LLM 추론은 Tailscale 너머 Windows GPU에서. keep_alive, 재시도, 체크포인트(재개).

실행:
  python scripts/judge_pool_qwen.py [--resume] [--max-pairs N]
  python scripts/judge_pool_qwen.py --aggregate-only   # 채점 건너뛰고 집계만

산출:
  checkpoints/fair_pool_qwen.json     (qwen 점수)
  qrels_pooled_3judge.tsv             (원본 qrels + 신규쌍 median rel)
  fair_pool_3judge_report.json        (3-채점관 κ, rel 분포)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.relabel_new_qrels_v3 import SYSTEM_PROMPT, _extract_score, load_corpus, load_queries
from scripts.validate_fair_pool_3model import cohen_linear, fleiss_kappa

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
POOL_PATH = DATA_DIR / "pool_to_judge.tsv"
QRELS_PATH = DATA_DIR / "qrels.tsv"
LABEL_CKPT = DATA_DIR / "checkpoints" / "fair_pool.json"        # exaone+gemma (입력)
QWEN_CKPT = DATA_DIR / "checkpoints" / "fair_pool_qwen.json"    # qwen (산출)
OUT_QRELS = DATA_DIR / "qrels_pooled_3judge.tsv"
OUT_REPORT = DATA_DIR / "fair_pool_3judge_report.json"

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://100.71.35.78:11434").rstrip("/") + "/api/generate"
QWEN_MODEL = "qwen2.5:14b"
JUDGES = ["exaone3.5:7.8b", "gemma3:12b", QWEN_MODEL]
MAX_CHARS = 600
CHECKPOINT_EVERY = 10


def call_qwen(prompt: str, retries: int = 4, timeout: int = 120) -> int | None:
    for attempt in range(retries):
        try:
            payload = json.dumps({
                "model": QWEN_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "10m",
                "options": {"temperature": 0.0, "num_predict": 128, "num_ctx": 4096},
            }).encode("utf-8")
            req = urllib.request.Request(
                OLLAMA_URL, data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8")).get("response", "")
            return _extract_score(raw)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(min(2 ** attempt, 8))
            else:
                print(f"    [qwen] 최종 실패: {e}")
    return None


def build_prompt(query_text: str, chunk_text: str) -> str:
    q = query_text[:MAX_CHARS].replace("\n", " / ")
    c = chunk_text[:MAX_CHARS]
    return f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"


def load_pool() -> list[tuple[str, str]]:
    pairs = []
    with POOL_PATH.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            p = line.rstrip("\n").split("\t")
            if i == 0 or len(p) < 2:
                continue
            pairs.append((p[0], p[1]))
    return pairs


def agg_median(scores: list[int | None]) -> int:
    """유효 점수의 중앙값(짝수면 floor). 전부 None이면 0."""
    valid = [s for s in scores if s is not None]
    if not valid:
        return 0
    return int(math.floor(statistics.median(valid)))


def aggregate_and_write() -> dict:
    ex_gem = json.loads(LABEL_CKPT.read_text(encoding="utf-8"))
    qwen = json.loads(QWEN_CKPT.read_text(encoding="utf-8")) if QWEN_CKPT.exists() else {}

    # 원본 qrels 보존 + 기존 쌍 집합
    existing, lines = set(), []
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            raw = line.rstrip("\n"); p = raw.split("\t")
            if i == 0 and p[0].lower() in {"qid", "query_id"}:
                lines.append(raw); continue
            if len(p) == 4:
                existing.add((p[0], p[2]))
            elif len(p) == 3:
                existing.add((p[0], p[1]))
            lines.append(raw)
    if not lines or lines[0].split("\t")[0].lower() not in {"qid", "query_id"}:
        lines.insert(0, "query_id\t0\tchunk_id\trelevance")

    triples, added, rel_dist = [], 0, Counter()
    for key in ex_gem:
        qid, docid = key.split("::", 1)
        ex = ex_gem[key].get("exaone3.5:7.8b")
        gm = ex_gem[key].get("gemma3:12b")
        qw = qwen.get(key)
        rel = agg_median([ex, gm, qw])
        rel_dist[rel] += 1
        if None not in (ex, gm, qw):
            triples.append((ex, gm, qw))
        if (qid, docid) not in existing:
            lines.append(f"{qid}\t0\t{docid}\t{rel}")
            added += 1
    OUT_QRELS.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ex_l = [t[0] for t in triples]; gm_l = [t[1] for t in triples]; qw_l = [t[2] for t in triples]
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "judges": JUDGES,
        "aggregation": "median(3 judges), floor on tie",
        "n_pool": len(ex_gem),
        "n_qwen_scored": sum(1 for v in qwen.values() if v is not None),
        "n_triple_valid": len(triples),
        "rel_distribution": dict(sorted(rel_dist.items())),
        "inter_rater_agreement": {
            "fleiss_kappa": round(fleiss_kappa(triples), 4),
            "cohen_kappa_ex_gem": round(cohen_linear(ex_l, gm_l), 4),
            "cohen_kappa_ex_qwen": round(cohen_linear(ex_l, qw_l), 4),
            "cohen_kappa_gem_qwen": round(cohen_linear(gm_l, qw_l), 4),
        },
        "added_pairs": added,
        "note": "ax4(검증자) 폐기. 3 채점관 중앙값이 라벨, 상호 κ가 검증 지표.",
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--aggregate-only", action="store_true")
    args = ap.parse_args()

    if not args.aggregate_only:
        queries = load_queries()
        corpus = load_corpus()
        pool = load_pool()
        done = json.loads(QWEN_CKPT.read_text(encoding="utf-8")) if (args.resume and QWEN_CKPT.exists()) else {}

        print("=" * 60)
        print(f"3번째 채점관 {QWEN_MODEL} @ {OLLAMA_URL}")
        print(f"풀 {len(pool)}쌍 | qwen 완료 {len(done)} | 척도 0~2 (600자)")
        print("=" * 60)

        todo = [p for p in pool if f"{p[0]}::{p[1]}" not in done]
        if args.max_pairs > 0:
            todo = todo[:args.max_pairs]
        print(f"이번 실행: {len(todo)}쌍\n")

        started = time.perf_counter()
        for idx, (qid, docid) in enumerate(todo, 1):
            qtext, ctext = queries.get(qid, ""), corpus.get(docid, "")
            key = f"{qid}::{docid}"
            done[key] = None if (not qtext or not ctext) else call_qwen(build_prompt(qtext, ctext))
            if idx % CHECKPOINT_EVERY == 0 or idx == len(todo):
                QWEN_CKPT.parent.mkdir(parents=True, exist_ok=True)
                QWEN_CKPT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
                rate = idx / (time.perf_counter() - started)
                eta = (len(todo) - idx) / rate / 60 if rate else 0
                print(f"  [qwen] {idx}/{len(todo)} {key}={done[key]} | {rate:.2f}쌍/s ETA {eta:.0f}분")
        QWEN_CKPT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")

    report = aggregate_and_write()
    ag = report["inter_rater_agreement"]
    print(f"\n{'='*60}\n3-채점관 집계 완료 (median)")
    print(f"  qwen 채점: {report['n_qwen_scored']}/{report['n_pool']} | 3중유효 {report['n_triple_valid']}")
    print(f"  신규 풀 rel 분포: {report['rel_distribution']}")
    print(f"  Fleiss κ(3채점관): {ag['fleiss_kappa']}  (기존 감독검증 0.491 대비)")
    print(f"  Cohen κ ex-gem {ag['cohen_kappa_ex_gem']} | ex-qwen {ag['cohen_kappa_ex_qwen']} | gem-qwen {ag['cohen_kappa_gem_qwen']}")
    print(f"  qrels: {OUT_QRELS} (+{report['added_pairs']}쌍)")
    print(f"  리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()

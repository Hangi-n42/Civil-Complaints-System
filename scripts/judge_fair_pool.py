"""
공정 풀 LLM 판정 (build_fair_pool_qrels.py 산출물 → qrels_pooled.tsv).

기존 qrels를 만든 relabel_new_qrels_v3.py와 **동일한** 0~2 척도 프롬프트(SYSTEM_PROMPT),
점수 추출(_extract_score), floor(평균) 집계(aggregate_scores)를 재사용한다
→ 라벨 드리프트 없이 기존 판정과 호환.

LLM 추론은 Tailscale 너머 Windows 데스크톱(mingeon)의 Ollama GPU에서 수행한다.
  기본 OLLAMA_BASE_URL = http://100.71.35.78:11434
  환경변수로 변경 가능 (예: 로컬 테스트 시 http://localhost:11434).

특징: 호출 재시도(원격 단절 대비), 5건마다 체크포인트(재개 지원).

실행:
  python scripts/judge_fair_pool.py [--resume] [--max-pairs N] [--models exaone3.5:7.8b,gemma3:12b]

산출:
  data/evaluation/v3/checkpoints/fair_pool.json   (쌍별 모델점수 + 집계 rel)
  data/evaluation/v3/qrels_pooled.tsv             (기존 qrels + 신규 판정)
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from scripts.relabel_new_qrels_v3 import (
    SYSTEM_PROMPT,
    _extract_score,
    aggregate_scores,
    load_corpus,
    load_queries,
)

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
POOL_PATH = DATA_DIR / "pool_to_judge.tsv"
QRELS_PATH = DATA_DIR / "qrels.tsv"
OUT_PATH = DATA_DIR / "qrels_pooled.tsv"
CKPT_PATH = DATA_DIR / "checkpoints" / "fair_pool.json"

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://100.71.35.78:11434").rstrip("/") + "/api/generate"
DEFAULT_MODELS = ["exaone3.5:7.8b", "gemma3:12b"]
CHECKPOINT_EVERY = 5
MAX_CHARS = 600


def call_ollama(model: str, prompt: str, retries: int = 4, timeout: int = 90) -> int | None:
    for attempt in range(retries):
        try:
            payload = json.dumps({
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": "10m",  # 패스 내내 모델을 VRAM에 유지 (스왑 방지)
                "options": {"temperature": 0.0, "num_predict": 128},
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
                print(f"    [{model}] 최종 실패: {e}")
    return None


def build_prompt(query_text: str, chunk_text: str) -> str:
    q = query_text[:MAX_CHARS].replace("\n", " / ")
    c = chunk_text[:MAX_CHARS]
    return f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"


def load_pool() -> list[tuple[str, str]]:
    pairs = []
    with POOL_PATH.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            parts = line.rstrip("\n").split("\t")
            if i == 0 or len(parts) < 2:
                continue
            pairs.append((parts[0], parts[1]))
    return pairs


def load_ckpt() -> dict:
    if CKPT_PATH.exists():
        return json.loads(CKPT_PATH.read_text(encoding="utf-8"))
    return {}


def save_ckpt(done: dict) -> None:
    CKPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CKPT_PATH.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")


def write_qrels_pooled(done: dict) -> int:
    """기존 qrels.tsv 전체 + done의 신규 쌍을 합쳐 qrels_pooled.tsv 작성 (비파괴)."""
    existing = set()
    lines = []
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            raw = line.rstrip("\n")
            parts = raw.split("\t")
            if i == 0 and parts[0].lower() in {"qid", "query_id"}:
                lines.append(raw)
                continue
            if len(parts) == 4:
                existing.add((parts[0], parts[2]))
            elif len(parts) == 3:
                existing.add((parts[0], parts[1]))
            lines.append(raw)
    if not lines or "\t" not in lines[0] or lines[0].split("\t")[0].lower() not in {"qid", "query_id"}:
        lines.insert(0, "query_id\t0\tchunk_id\trelevance")

    added = 0
    for key, rec in done.items():
        qid, docid = key.split("::", 1)
        if (qid, docid) in existing:
            continue
        lines.append(f"{qid}\t0\t{docid}\t{rec['rel']}")
        added += 1
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    queries = load_queries()
    corpus = load_corpus()
    pool = load_pool()
    done = load_ckpt() if args.resume else {}

    print("=" * 60)
    print(f"공정 풀 판정 | 엔드포인트: {OLLAMA_URL}")
    print(f"모델: {', '.join(models)} | 척도 0~2 floor(평균)")
    print(f"풀 {len(pool)}쌍 | 체크포인트 완료 {len(done)}건")
    print("=" * 60)

    pairs = pool[:args.max_pairs] if args.max_pairs > 0 else pool
    print(f"대상 {len(pairs)}쌍 × {len(models)}모델 (모델별 그룹 처리로 스왑 방지)\n")

    # ── 모델별 1패스: 한 모델을 VRAM에 올린 채 전 쌍을 연속 호출 (스왑 없음) ──
    for model in models:
        pending = [(qid, docid) for qid, docid in pairs
                   if model not in done.get(f"{qid}::{docid}", {})]
        print(f"── [{model}] {len(pending)}쌍 판정 ──")
        started = time.perf_counter()
        for idx, (qid, docid) in enumerate(pending, 1):
            key = f"{qid}::{docid}"
            rec = done.setdefault(key, {})
            qtext = queries.get(qid, "")
            ctext = corpus.get(docid, "")
            if not qtext or not ctext:
                rec[model] = None
                rec["note"] = "missing_text"
            else:
                rec[model] = call_ollama(model, build_prompt(qtext, ctext))
            if idx % CHECKPOINT_EVERY == 0 or idx == len(pending):
                save_ckpt(done)
                rate = idx / (time.perf_counter() - started)
                eta = (len(pending) - idx) / rate / 60 if rate else 0
                print(f"  [{model}] {idx}/{len(pending)} {key}={rec[model]} | {rate:.2f}쌍/s ETA {eta:.0f}분")
        save_ckpt(done)

    # ── 집계: floor(평균)으로 rel 재계산 ──
    for qid, docid in pairs:
        rec = done.get(f"{qid}::{docid}")
        if rec is not None:
            rec["rel"] = aggregate_scores({m: rec.get(m) for m in models})
    save_ckpt(done)
    added = write_qrels_pooled(done)
    rel_dist = {0: 0, 1: 0, 2: 0}
    for rec in done.values():
        rel_dist[rec["rel"]] = rel_dist.get(rec["rel"], 0) + 1
    print(f"\n[OK] 판정 완료 {len(done)}쌍 | rel 분포 {rel_dist}")
    print(f"[OK] qrels_pooled.tsv 작성: 신규 {added}쌍 추가 → {OUT_PATH}")
    print("재평가: QRELS_FILE=qrels_pooled.tsv python scripts/reranker_condensed_eval.py")


if __name__ == "__main__":
    main()

"""
리랭커 도메인 적응 fine-tune — (1) 학습 데이터셋 준비. (#270)

qrels_pooled_3judge.tsv(3채점관 median) + queries.jsonl + corpus_meta.json 에서
(query, doc, relevance) 학습쌍을 만들고 **쿼리 단위로 train/test를 분할**한다.
한 쿼리의 모든 쌍은 train 또는 test 한쪽에만 들어가 데이터 누수를 막는다.
(GPU 불필요 — Mac에서 실행)

산출: data/finetune/reranker/
  train.jsonl       학습쌍 {qid, docid, label(0/1/2), query, doc}
  train_qids.txt    학습 쿼리 id
  test_qids.txt     held-out 평가 쿼리 id (학습 금지)
  split_meta.json   seed·분할·라벨 분포
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "data" / "evaluation" / "v3"
OUT = ROOT / "data" / "finetune" / "reranker"

QRELS = V3 / "qrels_pooled_3judge.tsv"
QUERIES = V3 / "queries.jsonl"
CORPUS = V3 / "corpus_meta.json"

SEED = 42
TEST_RATIO = 0.20


def load_queries() -> dict[str, str]:
    out = {}
    with QUERIES.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                out[d["query_id"]] = d["query"]
    return out


def load_corpus() -> dict[str, str]:
    out = {}
    with CORPUS.open(encoding="utf-8") as f:
        for d in json.load(f):
            cid = d.get("case_id", "")
            if cid and cid not in out:
                out[cid] = d.get("chunk_text", "")
    return out


def load_qrels() -> list[tuple[str, str, int]]:
    rows = []
    with QRELS.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            p = line.strip().split("\t")
            if i == 0 and p[0].lower() in {"qid", "query_id"}:
                continue
            if len(p) == 4:
                rows.append((p[0], p[2], int(p[3])))
            elif len(p) == 3:
                rows.append((p[0], p[1], int(p[2])))
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    queries, corpus, qrels = load_queries(), load_corpus(), load_qrels()

    # 쿼리 단위 분할 (누수 방지)
    qids = sorted({q for q, _, _ in qrels if q in queries})
    rng = random.Random(SEED)
    rng.shuffle(qids)
    n_test = round(len(qids) * TEST_RATIO)
    test_qids = set(qids[:n_test])
    train_qids = set(qids[n_test:])

    # 학습쌍 추출 (train 쿼리만)
    train_rows, train_labels, skipped = [], Counter(), 0
    for qid, docid, rel in qrels:
        if qid not in train_qids:
            continue
        q, d = queries.get(qid, ""), corpus.get(docid, "")
        if not q or not d:
            skipped += 1
            continue
        train_rows.append({"qid": qid, "docid": docid, "label": rel, "query": q, "doc": d})
        train_labels[rel] += 1

    test_labels = Counter(rel for qid, _, rel in qrels if qid in test_qids)

    with (OUT / "train.jsonl").open("w", encoding="utf-8") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "train_qids.txt").write_text("\n".join(sorted(train_qids)) + "\n", encoding="utf-8")
    (OUT / "test_qids.txt").write_text("\n".join(sorted(test_qids)) + "\n", encoding="utf-8")

    meta = {
        "source_qrels": "qrels_pooled_3judge.tsv",
        "seed": SEED,
        "test_ratio": TEST_RATIO,
        "n_queries_total": len(qids),
        "n_train_queries": len(train_qids),
        "n_test_queries": len(test_qids),
        "n_train_pairs": len(train_rows),
        "train_label_dist": dict(sorted(train_labels.items())),
        "test_label_dist": dict(sorted(test_labels.items())),
        "skipped_missing_text": skipped,
        "note": "쿼리 단위 분할(누수 방지). self-doc(gen-origin rel=2)도 학습에 포함. 평가는 test_qids로만.",
    }
    (OUT / "split_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 56)
    print(f"쿼리 {len(qids)} → train {len(train_qids)} / test {len(test_qids)} (seed {SEED})")
    print(f"학습쌍 {len(train_rows)} | 라벨 {dict(sorted(train_labels.items()))} | skip {skipped}")
    print(f"test 라벨 {dict(sorted(test_labels.items()))}")
    print(f"산출: {OUT}")
    print("=" * 56)


if __name__ == "__main__":
    main()

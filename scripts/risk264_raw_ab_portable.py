"""
Issue #264 A/B (자체완결/portable 버전 — GPU 머신용)

두 변형을 모두 GPU에서 새로 임베딩하여 비교한다 (기존 civil_cases_v1 ChromaDB 불필요).
  - V_4elem : 현행 코퍼스 포맷 (4요소 chunk_text)
  - V_raw   : build_index.py 포맷 근사 ([원문] + 4요소)

in-memory(Ephemeral) ChromaDB 컬렉션을 사용하므로 디스크/운영 코퍼스에 흔적 없음.

필요 파일: data/evaluation/v3/{corpus_meta.json, queries.jsonl, qrels.tsv}
           data/Public_Civil_Service_LLM_Data/*/01.원천데이터/*.zip
실행: python scripts/risk264_raw_ab_portable.py
산출: reports/retrieval/v3/risk264_raw_ab.json
"""
from __future__ import annotations

import json
import time
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    load_queries,
    load_qrels,
    compute_metrics,
    build_run,
    dedup_to_case,
    chunk_to_case,
    _pick_embedding_device,
    TOP_K,
)
from app.ingestion.service import IngestionService
from app.core.config import settings

REPORT = Path(__file__).resolve().parents[1] / "reports" / "retrieval" / "v3" / "risk264_raw_ab.json"
CORPUS_META = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "v3" / "corpus_meta.json"


def build_raw_map() -> dict[str, dict]:
    # 원천 zip 위치: data/Public_Civil_Service_LLM_Data/ 하위 어디든(재귀) 또는 data/source_zips/
    root = Path(__file__).resolve().parents[1] / "data"
    bases = [root / "Public_Civil_Service_LLM_Data", root / "source_zips"]
    zips = []
    for base in bases:
        if base.exists():
            zips.extend(sorted(base.rglob("*.zip")))
    raw_map: dict[str, dict] = {}
    for zp in zips:
        z = zipfile.ZipFile(zp)
        for n in z.namelist():
            if not n.endswith(".json"):
                continue
            try:
                rec = json.loads(z.read(n).decode("utf-8"))
            except UnicodeDecodeError:
                rec = json.loads(z.read(n).decode("cp949"))
            for r in (rec if isinstance(rec, list) else [rec]):
                sid = str(r.get("source_id", "")).strip()
                if sid:
                    raw_map[sid] = r
    return raw_map


def _m(d: dict, k: str) -> float:
    for kk, vv in d.items():
        if kk.lower() == k.lower():
            return vv
    return next((v for kk, v in d.items() if k.lower() in kk.lower()), 0.0)


def embed_collection(client, model, name, ids, texts, metas, batch=16):
    try:
        client.delete_collection(name)
    except Exception:
        pass
    col = client.create_collection(name, metadata={"hnsw:space": "cosine"})
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # 패딩 낭비 최소화
    t0 = time.perf_counter()
    for b in range(0, len(order), batch):
        idxs = order[b:b + batch]
        embs = model.encode([texts[i] for i in idxs], batch_size=batch,
                            normalize_embeddings=True, show_progress_bar=False).tolist()
        col.add(ids=[ids[i] for i in idxs], embeddings=embs, metadatas=[metas[i] for i in idxs])
        if (b // batch) % 8 == 0:
            print(f"   [{name}] {min(b+batch,len(order))}/{len(texts)} ({time.perf_counter()-t0:.0f}s)", flush=True)
    print(f"   [{name}] 완료 ({time.perf_counter()-t0:.0f}s)", flush=True)
    return col


def dense_eval(col, model, queries):
    runs = {}
    for q in queries:
        emb = model.encode([q["query"]], normalize_embeddings=True)[0].tolist()
        res = col.query(query_embeddings=[emb], n_results=TOP_K * 3, include=["distances", "metadatas"])
        ids, dists, metas = res["ids"][0], res["distances"][0], res["metadatas"][0]
        hits = [(meta.get("case_id") or chunk_to_case(cid), 1.0 - float(d))
                for cid, d, meta in zip(ids, dists, metas)]
        runs[q["query_id"]] = build_run(q["query_id"], dedup_to_case(hits)[:TOP_K])
    return runs


def main() -> None:
    import chromadb
    from sentence_transformers import SentenceTransformer

    queries = load_queries()
    qrels = load_qrels()
    corpus = json.load(open(CORPUS_META, encoding="utf-8"))
    print(f"쿼리 {len(queries)} / qrels {len(qrels)} / corpus {len(corpus)}")

    print("[1] 원천 원문 맵...")
    raw_map = build_raw_map()
    ing = IngestionService()

    print("[2] 문서 텍스트 생성 (4요소 / [원문]+4요소)...")
    ids, metas, t_4elem, t_raw = [], [], [], []
    missing = 0
    import statistics
    raw_lens = []
    for d in corpus:
        sid = str(d.get("source_id", "")).strip()
        rec = raw_map.get(sid)
        raw_text = ing.normalize_aihub_record(rec).get("text", "") if rec else ""
        if not rec:
            missing += 1
        raw_lens.append(len(raw_text))
        ids.append(d["chunk_id"])
        metas.append({"case_id": d["case_id"]})
        t_4elem.append(d["chunk_text"])
        t_raw.append(f"[원문]\n{raw_text}\n{d['chunk_text']}" if raw_text else d["chunk_text"])
    print(f"   원문 누락 {missing}, 평균 {statistics.mean(raw_lens):.0f}자 (중앙값 {statistics.median(raw_lens):.0f}, 최대 {max(raw_lens)})")

    device = _pick_embedding_device()
    print(f"[3] BGE-m3 임베딩 (device={device})...")
    model = SentenceTransformer(settings.EMBEDDING_MODEL, device=device)
    # VRAM 12GB(+Ollama 점유) 대응: 최장 시퀀스 길이 제한 (최대 원문~2050토큰이라 손실 거의 없음)
    model.max_seq_length = min(model.max_seq_length, 2048)
    client = chromadb.EphemeralClient()

    col_4 = embed_collection(client, model, "ab_4elem", ids, t_4elem, metas)
    col_r = embed_collection(client, model, "ab_raw", ids, t_raw, metas)

    print("[4] Dense 평가...")
    m4 = compute_metrics(dense_eval(col_4, model, queries), qrels)
    mr = compute_metrics(dense_eval(col_r, model, queries), qrels)

    print("\n" + "=" * 58)
    print(f"{'metric':<10}{'4요소(현행)':>14}{'[원문]+4요소':>15}{'Δ':>10}")
    print("-" * 49)
    for k in ["nDCG@5", "nDCG@10", "R@10", "AP@10", "P@5"]:
        a, b = _m(m4, k), _m(mr, k)
        print(f"{k:<10}{a:>14.4f}{b:>15.4f}{b-a:>+10.4f}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "device": device,
        "n_queries": len(queries),
        "raw_missing": missing,
        "raw_text_median_chars": statistics.median(raw_lens),
        "v_4elem": m4,
        "v_raw_plus_4elem": mr,
        "note": "양 변형 모두 GPU에서 동일 BGE-m3로 신규 임베딩(Ephemeral). 포맷 변수만 격리.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {REPORT}")


if __name__ == "__main__":
    main()

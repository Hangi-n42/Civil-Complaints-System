"""
Issue #264 A/B: 원문 포함 vs 미포함 임베딩 비교

목적: build_index.py가 임베딩하는 [원문]+4요소 포맷이 현행 4요소-only 코퍼스 대비
      검색 성능을 높이는지/낮추는지 측정하여 정규 포맷 결정에 데이터 제공.

방법 (포맷 변수만 격리, EXAONE 재구조화 없음):
  - 기존 4요소(corpus_meta.chunk_text)는 그대로 사용
  - 원천 zip에서 source_id로 원문 복원 → IngestionService.normalize_aihub_record()['text']
  - 변형 doc = "[원문]\n{raw}\n{기존 4요소}" 를 임시 컬렉션에 BGE-m3 임베딩
  - run_dense로 현행(civil_cases_v1) vs 변형(civil_cases_ab_raw) 비교

산출물: reports/retrieval/v3/risk264_raw_ab.json
"""
from __future__ import annotations
import json, time, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_v3_evaluation import (
    load_queries, load_qrels, run_dense, compute_metrics, _pick_embedding_device,
)
from app.ingestion.service import IngestionService
from app.core.config import settings

AB_COLLECTION = "civil_cases_ab_raw"
REPORT = Path("reports/retrieval/v3/risk264_raw_ab.json")


def build_raw_map() -> dict[str, dict]:
    base = Path("data/Public_Civil_Service_LLM_Data")
    raw_map: dict[str, dict] = {}
    for zp in base.glob("*/01.원천데이터/*.zip"):
        z = zipfile.ZipFile(zp)
        for n in z.namelist():
            if not n.endswith(".json"):
                continue
            try:
                rec = json.loads(z.read(n).decode("utf-8"))
            except UnicodeDecodeError:
                rec = json.loads(z.read(n).decode("cp949"))
            recs = rec if isinstance(rec, list) else [rec]
            for r in recs:
                sid = str(r.get("source_id", "")).strip()
                if sid:
                    raw_map[sid] = r
    return raw_map


def _m(d, k):
    for kk, vv in d.items():
        if kk.lower() == k.lower():
            return vv
    return next((v for kk, v in d.items() if k.lower() in kk.lower()), 0.0)


def main() -> None:
    import chromadb
    from sentence_transformers import SentenceTransformer
    import torch

    queries = load_queries()
    qrels = load_qrels()
    corpus = json.load(open("data/evaluation/v3/corpus_meta.json"))
    print(f"쿼리 {len(queries)} / qrels {len(qrels)} / corpus {len(corpus)}")

    print("[1] 원천 원문 맵 구축...")
    raw_map = build_raw_map()
    ing = IngestionService()

    print("[2] 변형 문서 텍스트 생성 ([원문]+4요소)...")
    ab_ids, ab_texts, ab_metas = [], [], []
    missing = 0
    raw_lens = []
    for d in corpus:
        sid = str(d.get("source_id", "")).strip()
        rec = raw_map.get(sid)
        if not rec:
            missing += 1
            raw_text = ""
        else:
            raw_text = ing.normalize_aihub_record(rec).get("text", "")
        raw_lens.append(len(raw_text))
        combined = f"[원문]\n{raw_text}\n{d['chunk_text']}" if raw_text else d["chunk_text"]
        ab_ids.append(d["chunk_id"])
        ab_texts.append(combined)
        ab_metas.append({"case_id": d["case_id"]})
    import statistics
    print(f"   원문 누락 {missing}건, 원문 평균길이 {statistics.mean(raw_lens):.0f}자 "
          f"(중앙값 {statistics.median(raw_lens):.0f}, 최대 {max(raw_lens)})")

    device = _pick_embedding_device()
    print(f"[3] BGE-m3 임베딩 + 임시 컬렉션 적재... (device={device})")
    model = SentenceTransformer(settings.EMBEDDING_MODEL, device=device)
    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    try:
        client.delete_collection(AB_COLLECTION)
    except Exception:
        pass
    col = client.create_collection(AB_COLLECTION, metadata={"hnsw:space": "cosine"})

    # 길이순 정렬: 배치 내 길이 편차를 줄여 패딩 낭비 최소화 (MPS 처리량 향상)
    order = sorted(range(len(ab_texts)), key=lambda i: len(ab_texts[i]))
    BATCH = 256
    t0 = time.perf_counter()
    for b in range(0, len(order), BATCH):
        idxs = order[b:b + BATCH]
        chunk = [ab_texts[i] for i in idxs]
        embs = model.encode(
            chunk, batch_size=BATCH, normalize_embeddings=True, show_progress_bar=False
        ).tolist()
        col.add(
            ids=[ab_ids[i] for i in idxs],
            embeddings=embs,
            metadatas=[ab_metas[i] for i in idxs],
        )
        if (b // BATCH) % 5 == 0:
            done = min(b + BATCH, len(order))
            print(f"   {done}/{len(ab_texts)} ({time.perf_counter()-t0:.0f}s)", flush=True)
    print(f"   임베딩 완료 ({time.perf_counter()-t0:.0f}s)")

    print("[4] Dense 평가 — 현행(civil_cases_v1) vs 변형([원문]+4요소)...")
    cur_runs = run_dense(queries, collection_name="civil_cases_v1")
    cur_m = compute_metrics(cur_runs, qrels)
    ab_runs = run_dense(queries, collection_name=AB_COLLECTION)
    ab_m = compute_metrics(ab_runs, qrels)

    print("\n" + "=" * 60)
    print(f"{'metric':<10}{'현행(4요소)':>14}{'[원문]+4요소':>15}{'Δ':>10}")
    print("-" * 49)
    for k in ["nDCG@5", "nDCG@10", "R@10", "AP@10", "P@5"]:
        a, b = _m(cur_m, k), _m(ab_m, k)
        print(f"{k:<10}{a:>14.4f}{b:>15.4f}{b-a:>+10.4f}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_queries": len(queries),
        "raw_missing": missing,
        "raw_text_median_chars": statistics.median(raw_lens),
        "current_4elem": cur_m,
        "raw_plus_4elem": ab_m,
        "note": "포맷 변수만 격리(기존 4요소 재사용). build_index.py는 추가로 라벨([관찰] 등)·빈요소필터 적용.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {REPORT}")
    # 임시 컬렉션 정리
    try:
        client.delete_collection(AB_COLLECTION)
        print(f"임시 컬렉션 {AB_COLLECTION} 삭제 완료")
    except Exception:
        pass


if __name__ == "__main__":
    main()

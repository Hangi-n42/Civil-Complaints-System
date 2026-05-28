"""
V3 평가셋 쿼리 확장 스크립트  49 → ~112건

파이프라인:
1. 원천데이터(01.원천데이터) 샘플링 — 라벨링 데이터(02.라벨링데이터)는 제외
2. BE1 Ingestion(normalize_aihub_record + clean_text + mask_pii)
3. BE1 Structuring(Stage1 NER + Stage2 LLM EXAONE + Stage3 Merger) → 4요소
4. 4요소 텍스트를 쿼리 문자열로 포매팅
5. ChromaDB BM25 + Dense top-20 풀링 (동일 source_id leak 방지)
6. gemma3:12b LLM 라벨링 (0/1/2점)
7. queries.jsonl / qrels.tsv 업데이트
"""

from __future__ import annotations

import asyncio
import json
import math
import pathlib
import random
import re
import sys
import time
from collections import Counter

import ollama

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.ingestion.service import IngestionService
from app.structuring.service import StructuringService

DATA_DIR = PROJECT_ROOT / "data" / "evaluation" / "v3"
# 원천 데이터만 사용 (라벨링 데이터 폴더 제외)
RAW_SUBDIR = "01.원천데이터"
RAW_DIR = PROJECT_ROOT / "data" / "Public_Civil_Service_LLM_Data"

SEED = 42
POOL_K = 20          # BM25, Dense 각각 top-K

# 기존 v3와 동일한 3개 LLM + 다수결 방식 (local_validity_report_gemma3.json 기준)
LABEL_MODELS = [
    "exaone3.5:7.8b",
    "gemma3:12b",
    "ax4-light-local:latest",
]

# 소스별 신규 추가 목표 (기존 49 + 63 = 112건)
TARGET_NEW: dict[str, int] = {
    "고용노동부": 11,
    "국립아시아문화전당": 11,
    "국토교통부": 10,
    "성남시": 10,
    "안양시": 10,
    "중소벤처기업부": 11,
}


# ──────────────────────────────────────────────
# 1. 샘플링 (원천데이터만)
# ──────────────────────────────────────────────

def load_existing_queries() -> list[dict]:
    with (DATA_DIR / "queries.jsonl").open("r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def sample_new_cases(existing_queries: list[dict]) -> list[dict]:
    """01.원천데이터 폴더에서 미사용 사례를 소스별 목표 수만큼 샘플링."""
    used_ids = {q["source_id"] for q in existing_queries}
    pool: dict[str, list[dict]] = {src: [] for src in TARGET_NEW}

    for split in ["Training", "Validation"]:
        raw_base = RAW_DIR / split / RAW_SUBDIR
        if not raw_base.exists():
            continue
        for src_dir in raw_base.iterdir():
            for f_path in src_dir.rglob("*.json"):
                with open(f_path, encoding="utf-8") as fh:
                    records = json.load(fh)
                for rec in records:
                    src = rec.get("source", "")
                    sid = str(rec.get("source_id", ""))
                    if src in pool and sid not in used_ids:
                        pool[src].append(rec)

    rng = random.Random(SEED)
    sampled: list[dict] = []
    for src, recs in pool.items():
        rng.shuffle(recs)
        sampled.extend(recs[: TARGET_NEW[src]])
        print(f"  {src}: {min(TARGET_NEW[src], len(recs))}건 샘플링 (후보 {len(recs)}건)")

    print(f"[샘플링] 신규 후보: {len(sampled)}건")
    return sampled


# ──────────────────────────────────────────────
# 2–4. BE1 파이프라인 → 쿼리 텍스트 생성
# ──────────────────────────────────────────────

def _format_query_text(structured: dict) -> str:
    """구조화 결과의 4요소를 쿼리 문자열로 포매팅.

    기존 v3 쿼리와 동일 형식: 각 요소 텍스트를 줄바꿈으로 연결.
    """
    parts: list[str] = []
    for key in ("observation", "result", "request", "context"):
        elem = structured.get(key)
        if isinstance(elem, dict):
            text = (elem.get("text") or "").strip()
        else:
            text = str(elem or "").strip()
        # LLM이 빈 요소를 "null"/"none" 문자열로 반환하는 경우 placeholder로 처리 (issue #265)
        if text and text.lower() not in ("null", "none", "n/a"):
            parts.append(text)
    return "\n".join(parts)


async def _generate_query_from_record(
    rec: dict,
    ingest_svc: IngestionService,
    struct_svc: StructuringService,
) -> dict | None:
    """단일 원천 레코드를 ingestion + structuring 파이프라인에 통과시켜 쿼리 dict 반환."""
    try:
        normed = ingest_svc.normalize_aihub_record(rec)
        normed["text"] = await ingest_svc.clean_text(normed["raw_text"])
        normed["text"] = await ingest_svc.mask_pii(normed["text"])
        normed["raw_text"] = normed["text"]

        structured = await struct_svc.structure(normed)

        query_text = _format_query_text(structured)
        if not query_text:
            return None

        return {
            "source_id": str(rec.get("source_id", "")),
            "source": rec.get("source", ""),
            "category": rec.get("consulting_category", ""),
            "query": query_text,
        }
    except Exception as e:
        print(f"    [경고] 구조화 실패 ({rec.get('source_id','?')}): {e}")
        return None


async def generate_queries_async(cases: list[dict], start_qid: int) -> list[dict]:
    ingest_svc = IngestionService()
    struct_svc = StructuringService()

    results: list[dict] = []
    for i, rec in enumerate(cases, 1):
        q_dict = await _generate_query_from_record(rec, ingest_svc, struct_svc)
        if q_dict:
            qid = f"Q-{start_qid + len(results):04d}"
            q_dict["query_id"] = qid
            results.append(q_dict)

        if i % 10 == 0 or i == len(cases):
            print(f"  [{i}/{len(cases)}] 성공 {len(results)}건")

    print(f"[쿼리 생성] {len(results)}/{len(cases)}건 성공")
    return results


def generate_queries(cases: list[dict], start_qid: int) -> list[dict]:
    return asyncio.run(generate_queries_async(cases, start_qid))


# ──────────────────────────────────────────────
# 5. ChromaDB 풀링
# ──────────────────────────────────────────────

class BM25:
    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(corpus)
        self.doc_freqs: list[Counter] = []
        self.doc_len: list[int] = []
        self.idf: dict[str, float] = {}
        self._build(corpus)

    def _tok(self, texts: list[str]) -> list[list[str]]:
        try:
            from app.retrieval.pipeline.stages.bm25_retriever import _tokenize_korean
            return _tokenize_korean(texts)
        except ImportError:
            return [re.findall(r"[A-Za-z0-9가-힣]+", t.lower()) for t in texts]

    def _build(self, corpus: list[str]) -> None:
        nd: dict[str, int] = {}
        for tokens in self._tok(corpus):
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            self.doc_len.append(sum(freq.values()))
            for w in freq:
                nd[w] = nd.get(w, 0) + 1
        self.avgdl = sum(self.doc_len) / self.n if self.n else 0
        for w, df in nd.items():
            self.idf[w] = math.log(((self.n - df + 0.5) / (df + 0.5)) + 1)

    def top_k(self, query: str, k: int) -> list[int]:
        scores = [0.0] * self.n
        for q in self._tok([query])[0]:
            idf = self.idf.get(q, 0.0)
            if not idf:
                continue
            for i in range(self.n):
                f = self.doc_freqs[i].get(q, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                scores[i] += idf * f * (self.k1 + 1) / denom
        return sorted(range(self.n), key=lambda i: scores[i], reverse=True)[:k]


def chunk_to_case(cid: str) -> str:
    if "::" in cid:
        return cid.split("::")[0]
    if "__chunk-" in cid:
        return cid.split("__chunk-")[0]
    return cid


def load_chroma_corpus() -> tuple[list[str], list[str], list[str], list[dict], "np.ndarray"]:
    """(ids, docs, case_ids, metas, corpus_embs) 반환. ChromaDB는 한 번만 열어 모두 로딩."""
    import chromadb
    import numpy as np

    print("[코퍼스] ChromaDB 로딩 중...")
    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    col = client.get_collection("civil_cases_v1")
    total = col.count()
    print(f"  총 청크: {total}")

    all_ids, all_docs, all_metas, emb_list = [], [], [], []
    batch = 5000
    for offset in range(0, total, batch):
        r = col.get(limit=batch, offset=offset, include=["documents", "metadatas", "embeddings"])
        all_ids.extend(r["ids"])
        all_docs.extend(r["documents"])
        all_metas.extend(r["metadatas"])
        emb_list.extend(r["embeddings"])

    all_case_ids = [
        m.get("case_id") or chunk_to_case(cid)
        for cid, m in zip(all_ids, all_metas)
    ]
    corpus_embs = np.array(emb_list, dtype=np.float32)
    print(f"  로딩 완료: {len(all_docs)}건, 임베딩: {corpus_embs.shape}")
    return all_ids, all_docs, all_case_ids, all_metas, corpus_embs


def build_pool(
    new_queries: list[dict],
    all_docs: list[str],
    all_case_ids: list[str],
    corpus_embs: "np.ndarray",
) -> dict[str, list[str]]:
    """BM25 + Dense 합집합 풀. 동일 source_id는 제외."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import torch

    # BM25
    print("[풀링] BM25 인덱스 구축...")
    bm25 = BM25(all_docs)

    print(f"  임베딩 행렬: {corpus_embs.shape}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[풀링] BGE-m3 쿼리 임베딩 ({device})...")
    embed_model = SentenceTransformer(settings.EMBEDDING_MODEL, device=device)

    pool: dict[str, list[str]] = {}
    for i, q in enumerate(new_queries, 1):
        qid = q["query_id"]
        q_source_id = q["source_id"]

        # BM25 top-K
        bm25_top = set(bm25.top_k(q["query"], POOL_K))

        # Dense top-K
        q_emb = embed_model.encode([q["query"]], normalize_embeddings=True)
        dense_scores = (q_emb @ corpus_embs.T).squeeze()
        dense_top = set(int(x) for x in np.argsort(dense_scores)[::-1][:POOL_K])

        # 합집합, leak 방지
        candidate_case_ids: list[str] = []
        seen: set[str] = set()
        for idx in bm25_top | dense_top:
            cid = all_case_ids[idx]
            # source_id → CASE-{source_id} 형식 매칭
            if q_source_id and q_source_id in cid:
                continue
            if cid not in seen:
                seen.add(cid)
                candidate_case_ids.append(cid)

        pool[qid] = candidate_case_ids
        if i % 10 == 0 or i == len(new_queries):
            print(f"  [{i}/{len(new_queries)}] 쿼리당 평균 후보: {sum(len(v) for v in pool.values())/len(pool):.1f}")

    return pool


# ──────────────────────────────────────────────
# 6. LLM 라벨링
# ──────────────────────────────────────────────

_LABEL_SYSTEM = """\
너는 민원 검색 시스템의 관련성 평가 전문가야.
기준 민원(Query)과 검색된 민원 사례(Chunk)를 보고 아래 기준으로 점수를 매겨.

2점: 핵심 쟁점이 같고 적용 법령·해결책도 같아 답변에 그대로 인용 가능.
1점: 같은 카테고리·주제지만 세부 상황이 달라 부분 참고만 가능.
0점: 키워드만 겹칠 뿐 실제 쟁점·행정절차가 달라 답변 오류를 유발할 수 있음.

출력 형식: 첫 줄에 숫자(0, 1, 2)만, 둘째 줄에 한 문장 이유.
"""

_LABEL_USER_TMPL = """\
[기준 민원 Query]
{query}

[검색된 민원 Chunk]
{chunk}
"""


def _label_one_model(model: str, query: str, chunk: str, retries: int = 2) -> int:
    """단일 모델로 라벨링. 실패 시 -1 반환."""
    for attempt in range(retries + 1):
        try:
            resp = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": _LABEL_SYSTEM},
                    {"role": "user", "content": _LABEL_USER_TMPL.format(
                        query=query[:800], chunk=chunk[:800]
                    )},
                ],
                options={"temperature": 0.0, "num_predict": 60},
            )
            first = resp.message.content.strip().splitlines()[0].strip()
            m = re.search(r"[012]", first)
            if m:
                return int(m.group())
        except Exception as e:
            if attempt == retries:
                print(f"    [경고] {model} 라벨링 오류: {e}")
    return -1


def _label_majority(query: str, chunk: str) -> int:
    """4개 LLM 다수결로 최종 점수 결정. 기존 v3와 동일 방식."""
    scores = []
    for model in LABEL_MODELS:
        s = _label_one_model(model, query, chunk)
        if s >= 0:
            scores.append(s)

    if not scores:
        return -1

    # 다수결: 최빈값 (동점 시 상위 점수 우선)
    cnt = Counter(scores)
    max_count = max(cnt.values())
    candidates = [s for s, c in cnt.items() if c == max_count]
    return max(candidates)


def label_pool(
    new_queries: list[dict],
    pool: dict[str, list[str]],
    case_text_lookup: dict[str, str],
) -> list[tuple[str, str, int]]:
    qid_text = {q["query_id"]: q["query"] for q in new_queries}
    pairs = [(qid, cid) for qid, cids in pool.items() for cid in cids]
    print(f"[라벨링] 총 {len(pairs)}쌍 × {len(LABEL_MODELS)}모델 (다수결)...")

    results: list[tuple[str, str, int]] = []
    for i, (qid, cid) in enumerate(pairs, 1):
        chunk_text = case_text_lookup.get(cid, "")
        if not chunk_text:
            continue
        score = _label_majority(qid_text[qid], chunk_text)
        if score >= 0:
            results.append((qid, cid, score))
        if i % 50 == 0 or i == len(pairs):
            done_pct = i / len(pairs) * 100
            print(f"  [{i}/{len(pairs)}] {done_pct:.0f}%")

    score_dist = Counter(s for _, _, s in results)
    print(f"[라벨] 점수 분포: {dict(sorted(score_dist.items()))}")
    return results


# ──────────────────────────────────────────────
# 7. 저장
# ──────────────────────────────────────────────

def save_queries(existing: list[dict], new_queries: list[dict]) -> None:
    path = DATA_DIR / "queries.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for q in existing + new_queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"[저장] queries.jsonl: {len(existing) + len(new_queries)}건")


def save_qrels(new_labels: list[tuple[str, str, int]]) -> None:
    path = DATA_DIR / "qrels.tsv"
    with path.open("r", encoding="utf-8") as f:
        existing_lines = f.readlines()

    new_lines = [f"{qid}\t0\t{cid}\t{score}\n" for qid, cid, score in new_labels]

    with path.open("w", encoding="utf-8") as f:
        f.writelines(existing_lines)
        f.writelines(new_lines)

    print(f"[저장] qrels.tsv: 기존 {len(existing_lines)}행 + 신규 {len(new_lines)}행")


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("V3 쿼리 확장 시작")
    print("=" * 60)

    existing_queries = load_existing_queries()
    print(f"기존 쿼리: {len(existing_queries)}건")

    # 1. 샘플링 (원천데이터만)
    print("\n[1단계] 원천데이터 샘플링...")
    cases = sample_new_cases(existing_queries)

    # 2~4. BE1 파이프라인 → 쿼리 생성
    print("\n[2~4단계] Ingestion + Structuring (EXAONE)...")
    start_qid = max(int(q["query_id"].split("-")[1]) for q in existing_queries) + 1
    t0 = time.perf_counter()
    new_queries = generate_queries(cases, start_qid)
    print(f"  소요: {time.perf_counter() - t0:.0f}초")

    if not new_queries:
        print("[오류] 생성된 쿼리 없음. 중단.")
        return

    # 5. ChromaDB 풀링
    print("\n[5단계] ChromaDB 풀 구축...")
    _, all_docs, all_case_ids, _, corpus_embs = load_chroma_corpus()

    # case_id → 대표 텍스트 (첫 청크)
    case_text_lookup: dict[str, str] = {}
    for doc, cid in zip(all_docs, all_case_ids):
        if cid not in case_text_lookup:
            case_text_lookup[cid] = doc

    t0 = time.perf_counter()
    pool = build_pool(new_queries, all_docs, all_case_ids, corpus_embs)
    print(f"  소요: {time.perf_counter() - t0:.0f}초")

    # 6. LLM 라벨링
    print("\n[6단계] LLM 라벨링 (gemma3:12b)...")
    t0 = time.perf_counter()
    labels = label_pool(new_queries, pool, case_text_lookup)
    print(f"  소요: {time.perf_counter() - t0:.0f}초")

    # 7. 저장
    print("\n[7단계] 저장...")
    save_queries(existing_queries, new_queries)
    save_qrels(labels)

    print(f"\n완료:")
    print(f"  쿼리 {len(existing_queries)} → {len(existing_queries) + len(new_queries)}건")
    print(f"  qrels 신규 {len(labels)}행 추가")


if __name__ == "__main__":
    main()

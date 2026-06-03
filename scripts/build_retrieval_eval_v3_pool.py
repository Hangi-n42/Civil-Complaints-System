"""
Build V3 Retrieval Evaluation Pool

전체 ChromaDB(9,132건)를 코퍼스로 삼아
50개 평가 쿼리에 대해 BM25 + BGE-m3 Top-K 후보를 추출합니다.
- 라벨: 모두 -1(미라벨) 로 초기화 (LLM이 0~3점으로 채울 예정)
- Leak 방지: 동일 case_id(source_id)는 제외
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any

try:
    from sentence_transformers import SentenceTransformer
    import torch
except ImportError:
    SentenceTransformer = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data" / "evaluation"
V3_DIR = DATA_DIR / "v3"

TOP_K = 10  # 각 모델에서 Top-K 추출


class BM25:
    """간단한 인메모리 BM25 구현"""
    def __init__(self, corpus: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.avgdl = 0
        self.doc_freqs = []
        self.idf = {}
        self.doc_len = []
        self._initialize(corpus)

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[A-Za-z0-9가-힣]+", text.lower())

    def _initialize(self, corpus: List[str]):
        nd = {}
        num_doc = 0
        for document in corpus:
            self.doc_len.append(0)
            num_doc += len(document)
            frequencies = Counter(self._tokenize(document))
            self.doc_freqs.append(frequencies)
            for word, freq in frequencies.items():
                nd[word] = nd.get(word, 0) + 1
            self.doc_len[-1] = sum(frequencies.values())
        self.avgdl = num_doc / self.corpus_size if self.corpus_size else 0
        for word, freq in nd.items():
            self.idf[word] = math.log(((self.corpus_size - freq + 0.5) / (freq + 0.5)) + 1)

    def get_top_k(self, query: str, k: int) -> List[int]:
        scores = [0.0] * self.corpus_size
        q_tokens = self._tokenize(query)
        for q in q_tokens:
            if q not in self.idf:
                continue
            idf = self.idf[q]
            for i in range(self.corpus_size):
                f = self.doc_freqs[i].get(q, 0)
                if f == 0:
                    continue
                numerator = idf * f * (self.k1 + 1)
                denominator = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                scores[i] += numerator / denominator
        ranked = sorted(range(self.corpus_size), key=lambda i: scores[i], reverse=True)
        return ranked[:k]


def load_jsonl(path: Path) -> List[Any]:
    data = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def main():
    print("[*] V3 Pool 생성 시작 (전체 ChromaDB 대상)")
    V3_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 평가 쿼리 로드 (기존 V2 구조화 쿼리 재사용)
    queries_path = DATA_DIR / "v2" / "queries.jsonl"
    if not queries_path.exists():
        print(f"[!] 에러: {queries_path} 파일이 없습니다.")
        return
    queries = load_jsonl(queries_path)
    print(f"[*] 평가 쿼리 {len(queries)}건 로드 완료")

    # 2. ChromaDB에서 전체 코퍼스 로드
    import chromadb
    from app.core.config import settings

    print("[*] ChromaDB 전체 코퍼스 로드 중...")
    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    col = client.get_collection("civil_cases_v1")
    total = col.count()
    print(f"[*] 전체 문서 수: {total}건")

    # 배치로 전체 문서 가져오기
    all_docs = []
    all_metas = []
    all_ids = []
    batch_size = 1000
    offset = 0
    while offset < total:
        result = col.get(
            limit=batch_size,
            offset=offset,
            include=["documents", "metadatas", "embeddings"]
        )
        all_docs.extend(result["documents"])
        all_metas.extend(result["metadatas"])
        all_ids.extend(result["ids"])
        offset += batch_size
        print(f"  로드 진행: {min(offset, total)}/{total}")

    print(f"[*] 코퍼스 로드 완료: {len(all_docs)}건")

    # 3. BM25 초기화
    print("[*] BM25 초기화 중...")
    bm25 = BM25(all_docs)

    # 4. Dense (BGE-m3) 임베딩 - ChromaDB에 저장된 임베딩 활용
    import numpy as np
    if SentenceTransformer is None:
        print("[!] 에러: sentence-transformers가 없습니다.")
        return

    print("[*] BGE-m3 쿼리 임베딩 준비 중...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    embed_model = SentenceTransformer("BAAI/bge-m3", device=device)

    # ChromaDB에서 가져온 임베딩 행렬 구성
    corpus_embeddings = np.array(
        [result["embeddings"] for result in [col.get(ids=[id_], include=["embeddings"]) for id_ in all_ids[:1]]]
    )
    # 전체 임베딩을 배치로 가져오기
    print("[*] 코퍼스 임베딩 행렬 구성 중 (ChromaDB에서 직접 추출)...")
    emb_list = []
    offset = 0
    while offset < total:
        result = col.get(
            limit=batch_size,
            offset=offset,
            include=["embeddings"]
        )
        emb_list.extend(result["embeddings"])
        offset += batch_size
    corpus_embeddings = np.array(emb_list, dtype=np.float32)
    print(f"[*] 임베딩 행렬: {corpus_embeddings.shape}")

    # 5. 쿼리별 후보 추출
    qrels_lines = ["query_id\t0\tchunk_id\trelevance"]
    corpus_entries = []  # for labeling sheet

    # corpus.jsonl 저장용
    corpus_for_v3 = []
    for i, (doc, meta, cid) in enumerate(zip(all_docs, all_metas, all_ids)):
        corpus_for_v3.append({
            "chunk_id": meta.get("chunk_id", cid),
            "case_id": meta.get("case_id", ""),
            "source_id": meta.get("case_id", "").replace("CASE-", ""),
            "source": meta.get("source", ""),
            "category": meta.get("category", ""),
            "chunk_text": doc,
        })

    total_candidates = 0

    print("[*] 쿼리별 후보 추출 중...")
    for idx, q in enumerate(queries, 1):
        q_id = q["query_id"]
        q_text = q["query"]
        q_source_id = q.get("source_id", "")

        # BM25 Top-K
        bm25_top = bm25.get_top_k(q_text, TOP_K)

        # Dense Top-K
        q_emb = embed_model.encode([q_text], convert_to_tensor=False)
        q_emb = np.array(q_emb, dtype=np.float32)
        dense_scores = (q_emb @ corpus_embeddings.T).squeeze()
        dense_top = np.argsort(dense_scores)[::-1][:TOP_K].tolist()

        # 합집합 Pool
        pool_indices = set(bm25_top) | set(dense_top)

        for ci in pool_indices:
            c = corpus_for_v3[ci]
            c_case_id = c["case_id"]
            c_source_id = c["source_id"]

            # Leak 방지
            if q_source_id and c_source_id and q_source_id == c_source_id:
                continue

            qrels_lines.append(f"{q_id}\t0\t{c_case_id}\t-1")
            total_candidates += 1

        if idx % 10 == 0:
            print(f"  - {idx}/{len(queries)} 처리 완료")

    # 6. 저장
    # corpus.jsonl - 라벨링 시트 생성에 필요
    with (V3_DIR / "corpus_meta.json").open("w", encoding="utf-8") as f:
        json.dump(corpus_for_v3, f, ensure_ascii=False, indent=2)

    # queries.jsonl 복사
    import shutil
    shutil.copy(queries_path, V3_DIR / "queries.jsonl")

    qrels_path = V3_DIR / "qrels.tsv"
    qrels_path.write_text("\n".join(qrels_lines) + "\n", encoding="utf-8")

    print(f"\n[OK] V3 Pool 생성 완료!")
    print(f" - 총 평가 쿼리: {len(queries)}건")
    print(f" - 추출된 후보 총계: {total_candidates}건 (쿼리당 평균 {total_candidates/len(queries):.1f}건)")
    print(f" - 코퍼스: ChromaDB 전체 {total}건")
    print(f"\n산출물: {V3_DIR}")
    print(" 1) qrels.tsv (라벨링 대상, relevance=-1)")
    print(" 2) queries.jsonl, corpus_meta.json")


if __name__ == "__main__":
    main()

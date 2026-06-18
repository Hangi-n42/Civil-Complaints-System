"""BE1 메타데이터 soft rerank 평가 (#317).

평가:
  - 일반 검색: Hybrid vs Hybrid + metadata soft rerank
  - grounding: Hybrid vs Hybrid + metadata soft rerank vs LLM-filter cache projection

평가 데이터에는 PR #314 신규 메타데이터가 없으므로, BE1 deterministic enrichment와
category/source를 sidecar signals로 생성해 사용한다.

산출:
  - reports/retrieval/v3/metadata_soft_rerank_eval.json
  - reports/retrieval/v3/metadata_soft_rerank_summary.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.run_v3_evaluation as R
from app.core.config import settings
from app.evaluation.datasets import QrelRecord
from app.evaluation.metrics import RunRecord, evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.enrichment import build_key_terms, normalize_entity_texts
from app.structuring.legal_dictionary import get_legal_ref_matcher
from scripts.eval_hybrid_noself import rrf
from scripts.eval_noself import get, take_top
from scripts.grounding_topk_breakdown import load_rel_map
from scripts.run_v3_evaluation import load_corpus, load_queries, run_bm25, run_dense

OUT_JSON = ROOT / "reports" / "retrieval" / "v3" / "metadata_soft_rerank_eval.json"
OUT_MD = ROOT / "reports" / "retrieval" / "v3" / "metadata_soft_rerank_summary.md"
QRELS_PATH = ROOT / "data" / "evaluation" / "v3" / "qrels_pooled_3judge.tsv"
LLM_CACHE = ROOT / "data" / "evaluation" / "v3" / "checkpoints" / "llm_rerank_full.json"
EXISTING_GROUNDING = ROOT / "reports" / "retrieval" / "v3" / "grounding_filter_effect.json"

DEPTH = 50
RRF_K = 60
GROUNDING_K = 5
LLM_FILTER_POOL = 10
METRIC_KEYS = ["nDCG@5", "nDCG@10", "P@5", "R@10"]
SIGNAL_FIELDS = ["entity_texts", "legal_ref_names", "legal_ref_ids", "key_terms", "responsible_units"]


def _clean_list(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen = set()
    for value in values:
        text = " ".join(str(value or "").split())
        if not text or text in {"-", "unknown"}:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _split_signal_values(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [item for item in value.split("|") if item]
    else:
        raw_items = []
    return _clean_list(raw_items)


def _has_any_signal(signals: dict[str, list[str]]) -> bool:
    return any(signals.get(field) for field in SIGNAL_FIELDS)


def load_qrels_3judge() -> list[QrelRecord]:
    qrels: list[QrelRecord] = []
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        for lineno, raw in enumerate(f):
            parts = raw.strip().split("\t")
            if lineno == 0 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) == 4:
                qrels.append(QrelRecord(qid=parts[0], docid=parts[2], relevance=int(parts[3])))
            elif len(parts) == 3:
                qrels.append(QrelRecord(qid=parts[0], docid=parts[1], relevance=int(parts[2])))
    return qrels


def qrels_stats(qrels: list[QrelRecord]) -> dict[str, Any]:
    by_query: dict[str, list[QrelRecord]] = {}
    rel_distribution: Counter[int] = Counter()
    for row in qrels:
        by_query.setdefault(row.qid, []).append(row)
        rel_distribution[int(row.relevance)] += 1

    judged_counts = sorted(len(rows) for rows in by_query.values())
    positive_counts = sorted(sum(1 for row in rows if row.relevance >= 1) for rows in by_query.values())

    def median(values: list[int]) -> int:
        return values[len(values) // 2] if values else 0

    return {
        "qrels_path": str(QRELS_PATH.relative_to(ROOT)),
        "judged_pairs": len(qrels),
        "queries": len(by_query),
        "rel_distribution": {str(key): rel_distribution.get(key, 0) for key in [0, 1, 2]},
        "judged_per_query": {
            "min": judged_counts[0] if judged_counts else 0,
            "median": median(judged_counts),
            "max": judged_counts[-1] if judged_counts else 0,
        },
        "positive_per_query": {
            "min": positive_counts[0] if positive_counts else 0,
            "median": median(positive_counts),
            "max": positive_counts[-1] if positive_counts else 0,
        },
        "queries_without_positive": sum(1 for count in positive_counts if count == 0),
    }


def build_case_map(corpus: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    by_case: dict[str, dict[str, Any]] = {}
    for row in corpus:
        cid = str(row.get("case_id") or "")
        if not cid:
            continue
        slot = by_case.setdefault(
            cid,
            {
                "texts": [],
                "category": str(row.get("category") or ""),
                "source": str(row.get("source") or ""),
            },
        )
        text = str(row.get("chunk_text") or "").strip()
        if text:
            slot["texts"].append(text)
        if not slot.get("category") or slot.get("category") == "unknown":
            slot["category"] = str(row.get("category") or "")
        if not slot.get("source"):
            slot["source"] = str(row.get("source") or "")

    return {
        cid: {
            "text": "\n".join(data.get("texts") or []),
            "category": str(data.get("category") or ""),
            "source": str(data.get("source") or ""),
        }
        for cid, data in by_case.items()
    }


def build_signals(text: str, *, category: str = "", source: str = "") -> dict[str, list[str]]:
    entity_texts = normalize_entity_texts([], text)
    legal_refs = get_legal_ref_matcher().match(text)
    key_terms = build_key_terms(text, entity_texts, legal_refs)
    responsible_units = _clean_list([category, source])
    return {
        "entity_texts": _clean_list([item.get("text") for item in entity_texts]),
        "legal_ref_names": _clean_list([item.get("name") for item in legal_refs]),
        "legal_ref_ids": _clean_list([item.get("law_id") for item in legal_refs]),
        "key_terms": _clean_list(key_terms),
        "responsible_units": responsible_units,
    }


def signal_coverage(signals: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    counts = {field: sum(1 for sig in signals.values() if sig.get(field)) for field in SIGNAL_FIELDS}
    return {"n": len(signals), "non_empty_by_field": counts}


def load_chroma_signal_map(collection_name: str = "civil_cases_v1") -> dict[str, dict[str, list[str]]]:
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.CHROMA_DB_PATH))
    collection = client.get_collection(collection_name)
    total = collection.count()
    signals_by_case: dict[str, dict[str, list[str]]] = {}

    for offset in range(0, total, 1000):
        got = collection.get(
            limit=min(1000, total - offset),
            offset=offset,
            include=["metadatas"],
        )
        ids = got.get("ids") or []
        metadatas = got.get("metadatas") or []
        for storage_id, metadata in zip(ids, metadatas):
            meta = metadata or {}
            case_id = str(meta.get("case_id") or meta.get("doc_id") or "").strip()
            if not case_id:
                case_id = str(storage_id).split("::", 1)[0].strip()
            if not case_id:
                continue

            slot = signals_by_case.setdefault(case_id, {field: [] for field in SIGNAL_FIELDS})
            for field in SIGNAL_FIELDS:
                slot[field].extend(_split_signal_values(meta.get(field)))

    return {
        cid: {field: _clean_list(values) for field, values in signals.items()}
        for cid, signals in signals_by_case.items()
    }


def build_candidate_doc_signals(
    candidate_cases: set[str],
    case_map: dict[str, dict[str, str]],
    chroma_signals: dict[str, dict[str, list[str]]],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, Any]]:
    sidecar_signals: dict[str, dict[str, list[str]]] = {}
    actual_count = 0
    merged: dict[str, dict[str, list[str]]] = {}

    for cid in sorted(candidate_cases):
        actual = chroma_signals.get(cid, {})
        if _has_any_signal(actual):
            merged[cid] = actual
            actual_count += 1
            continue

        doc = case_map.get(cid, {})
        sidecar = build_signals(
            doc.get("text", ""),
            category=doc.get("category", ""),
            source=doc.get("source", ""),
        )
        sidecar_signals[cid] = sidecar
        merged[cid] = sidecar

    if actual_count:
        source = "chroma_metadata_with_sidecar_fallback"
        reason = "candidate case에 Chroma 검색 신호 metadata가 있으면 우선 사용하고, 누락 case만 deterministic sidecar로 보완"
    else:
        source = "deterministic_sidecar"
        reason = "Chroma 후보 metadata에 PR #314/#318 검색 신호가 없어 deterministic sidecar만 사용"

    return merged, {
        "candidate_signal_source": source,
        "reason": reason,
        "candidate_cases": len(candidate_cases),
        "candidate_cases_with_chroma_metadata_signals": actual_count,
        "candidate_cases_with_sidecar_fallback": len(candidate_cases) - actual_count,
        "chroma_signal_coverage": signal_coverage({cid: chroma_signals.get(cid, {}) for cid in candidate_cases}),
        "sidecar_fallback_coverage": signal_coverage(sidecar_signals),
        "final_candidate_signal_coverage": signal_coverage(merged),
        "responsible_units_source": "Chroma metadata 우선, 누락 시 category + source deterministic fallback",
    }


def apply_metadata_rerank(
    runs: dict[str, list[RunRecord]],
    query_signals: dict[str, dict[str, list[str]]],
    doc_signals: dict[str, dict[str, list[str]]],
) -> dict[str, list[RunRecord]]:
    service = RetrievalService()
    out: dict[str, list[RunRecord]] = {}
    for qid, recs in runs.items():
        items = [
            {
                "case_id": rec.docid,
                "doc_id": rec.docid,
                "score": rec.score,
                "rank": rec.rank,
                "metadata": doc_signals.get(rec.docid, {}),
            }
            for rec in sorted(recs, key=lambda row: row.rank)
        ]
        reranked = service._apply_metadata_soft_rerank(items, query_signals.get(qid, {}))
        out[qid] = [
            RunRecord(qid=qid, docid=str(item["case_id"]), score=float(item["score"]), rank=rank)
            for rank, item in enumerate(reranked, 1)
        ]
    return out


def metrics_for(runs: dict[str, list[RunRecord]], qrels: list[QrelRecord], self_doc: dict[str, str]) -> dict:
    qrels_noself = [row for row in qrels if self_doc.get(row.qid) != row.docid]
    flat = [row for recs in take_top(runs, self_doc, 10, drop_self=True).values() for row in recs]
    return evaluate_run(qrels_noself, flat)


def summarize_grounding_docs(per_query_docs: dict[str, list[str]], rel_map: dict[tuple[str, str], int]) -> dict:
    slots = Counter()
    q_harmful = 0
    q_empty = 0
    filled: list[int] = []
    for qid, docs in per_query_docs.items():
        if not docs:
            q_empty += 1
        filled.append(len(docs))
        harmful = 0
        for docid in docs:
            rel = rel_map.get((qid, docid))
            slots["unjudged" if rel is None else f"rel{rel}"] += 1
            if rel == 0:
                harmful += 1
        if harmful:
            q_harmful += 1
    total = sum(slots.values())
    n_queries = len(per_query_docs)
    return {
        "k": GROUNDING_K,
        "n_queries": n_queries,
        "total_slots": total,
        "slots": {key: slots.get(key, 0) for key in ["rel2", "rel1", "rel0", "unjudged"]},
        "rel0_rate": round(slots.get("rel0", 0) / total, 4) if total else 0.0,
        "useful_rate": round((slots.get("rel2", 0) + slots.get("rel1", 0)) / total, 4) if total else 0.0,
        "harmful_query_rate": round(q_harmful / n_queries, 4) if n_queries else 0.0,
        "empty_result_rate": round(q_empty / n_queries, 4) if n_queries else 0.0,
        "queries_empty": q_empty,
        "avg_filled": round(sum(filled) / n_queries, 3) if n_queries else 0.0,
    }


def top_docs_no_self(runs: dict[str, list[RunRecord]], self_doc: dict[str, str], k: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for qid, recs in runs.items():
        docs = []
        seen = set()
        for rec in sorted(recs, key=lambda row: row.rank):
            if rec.docid == self_doc.get(qid) or rec.docid in seen:
                continue
            seen.add(rec.docid)
            docs.append(rec.docid)
            if len(docs) >= k:
                break
        out[qid] = docs
    return out


def apply_llm_filter_cache(
    runs: dict[str, list[RunRecord]],
    self_doc: dict[str, str],
    cache: dict[str, int],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    out: dict[str, list[str]] = {}
    scored = 0
    missing = 0
    pool_total = 0
    for qid, recs in runs.items():
        pool = []
        seen = set()
        for rec in sorted(recs, key=lambda row: row.rank):
            if rec.docid == self_doc.get(qid) or rec.docid in seen:
                continue
            seen.add(rec.docid)
            pool.append(rec.docid)
            if len(pool) >= LLM_FILTER_POOL:
                break
        pool_total += len(pool)
        kept: list[tuple[str, float, int]] = []
        for idx, docid in enumerate(pool):
            score = cache.get(f"{qid}::{docid}")
            if score is None:
                missing += 1
                kept.append((docid, 0.5, idx))
            else:
                scored += 1
                if score >= 1:
                    kept.append((docid, float(score), idx))
        kept.sort(key=lambda row: (-row[1], row[2]))
        out[qid] = [docid for docid, _, _ in kept[:GROUNDING_K]]
    coverage = round(scored / pool_total, 4) if pool_total else 0.0
    return out, {"pool_total": pool_total, "scored": scored, "missing": missing, "coverage": coverage}


def load_existing_llm_filter_baseline() -> dict[str, Any] | None:
    if not EXISTING_GROUNDING.exists():
        return None
    data = json.loads(EXISTING_GROUNDING.read_text(encoding="utf-8"))
    return data.get("by_k", {}).get(str(GROUNDING_K), {}).get("Hybrid+LLM-filter")


def write_summary(report: dict[str, Any]) -> None:
    general = report["general_search"]
    grounding = report["grounding"]
    signals = report["signals"]
    reliability = report["reliability"]
    qrels = reliability["qrels_stats"]
    base = general["systems"]["Hybrid"]
    meta = general["systems"]["Hybrid+metadata_soft_rerank"]
    delta = general["delta"]
    g_base = grounding["systems"]["Hybrid"]
    g_meta = grounding["systems"]["Hybrid+metadata_soft_rerank"]
    g_filter = grounding["systems"]["Hybrid+metadata_soft_rerank+LLM_filter_cache_projection"]
    p5_delta_text = "그대로였다" if abs(delta["P@5"]) < 0.000001 else f"{delta['P@5']:+.4f} 변했다"
    rel0_delta = round(g_meta["rel0_rate"] - g_base["rel0_rate"], 6)
    if abs(rel0_delta) < 0.000001:
        rel0_text = "같았다"
    elif rel0_delta < 0:
        rel0_text = "감소했다"
    else:
        rel0_text = "증가했다"

    lines = [
        "# 메타데이터 soft rerank 평가 요약",
        "",
        f"- 평가셋: {report['eval_set']}",
        f"- 후보 깊이: Hybrid RRF top-{report['depth']}, RRF k={report['rrf_k']}",
        f"- 쿼리 신호: {signals['query_signal_source']} ({signals['query_signal_reason']})",
        f"- 후보 문서 신호: {signals['candidate_signal_source']} ({signals['reason']})",
        (
            f"- Chroma metadata 신호 사용 후보: "
            f"{signals['candidate_cases_with_chroma_metadata_signals']}/{signals['candidate_cases']}건"
        ),
        "",
        "## 결론",
        "",
        (
            f"- 일반 검색은 `nDCG@10` {delta['nDCG@10']:+.4f}, "
            f"`R@10` {delta['R@10']:+.4f}로 소폭 개선됐고 `P@5`는 {p5_delta_text}."
        ),
        (
            f"- 답변 초안 grounding에서는 metadata 단독 rel0 비율이 "
            f"{g_base['rel0_rate']:.4f} -> {g_meta['rel0_rate']:.4f}로 {rel0_text}."
        ),
        "- 따라서 grounding 기본값은 여전히 `Hybrid + LLM relevance filter`가 필요하다.",
        (
            "- `legal_ref_ids` 후보 coverage: "
            f"{signals['final_candidate_signal_coverage']['non_empty_by_field'].get('legal_ref_ids', 0)}건"
        ),
        "",
        "## 평가 신뢰도 해석",
        "",
        (
            f"- 현재 지표는 `{qrels['qrels_path']}`의 {qrels['queries']}개 쿼리, "
            f"{qrels['judged_pairs']}개 판정쌍을 기준으로 계산했다."
        ),
        (
            f"- relevance 분포: rel0={qrels['rel_distribution']['0']}, "
            f"rel1={qrels['rel_distribution']['1']}, rel2={qrels['rel_distribution']['2']}."
        ),
        "- 3-채점관 median, no-self 제거, Dense/BM25 공정 풀링을 사용해 기존 평가보다 방법론은 개선됐다.",
        "- 그래도 이 수치는 운영 품질의 최종 보증이 아니라, 검색 변경의 회귀 여부를 보는 방향성 지표로 해석해야 한다.",
        "- 이유: 쿼리가 실제 신규 민원 held-out이 아니고, query_signals는 실제 BE1 출력이 아니라 deterministic sidecar이며, 정답표는 top-50 풀 기반이라 long-tail 불완전성이 남아 있다.",
        "",
        "## 일반 검색",
        "",
        "| 지표 | Hybrid | Hybrid+metadata | 변화 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key in METRIC_KEYS:
        lines.append(f"| {key} | {get(base, key):.4f} | {get(meta, key):.4f} | {delta[key]:+.4f} |")

    lines.extend([
        "",
        "## 답변 초안 grounding 관점(top-5)",
        "",
        "| 방법 | rel0 비율 | rel0 포함 쿼리 비율 | 빈 결과 비율 | 평균 근거 수 |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| Hybrid | {g_base['rel0_rate']:.4f} | {g_base['harmful_query_rate']:.4f} | "
            f"{g_base['empty_result_rate']:.4f} | {g_base['avg_filled']:.2f} |"
        ),
        (
            f"| Hybrid+metadata | {g_meta['rel0_rate']:.4f} | {g_meta['harmful_query_rate']:.4f} | "
            f"{g_meta['empty_result_rate']:.4f} | {g_meta['avg_filled']:.2f} |"
        ),
        (
            f"| Hybrid+metadata+LLM cache filter | {g_filter['rel0_rate']:.4f} | "
            f"{g_filter['harmful_query_rate']:.4f} | {g_filter['empty_result_rate']:.4f} | "
            f"{g_filter['avg_filled']:.2f} |"
        ),
        "",
        "## 해석",
        "",
        "- metadata soft rerank는 hard filter가 아니므로 빈 결과를 만들지 않는다.",
        "- LLM filter cache projection은 기존 LLM 채점 캐시를 재사용한 분석이며, cache coverage를 함께 확인해야 한다.",
        f"- LLM cache coverage: {grounding['llm_cache']['coverage']:.4f} "
        f"({grounding['llm_cache']['scored']}/{grounding['llm_cache']['pool_total']})",
    ])
    existing = grounding.get("existing_hybrid_llm_filter_baseline")
    if existing:
        lines.extend([
            "",
            "## 기존 LLM filter 기준선",
            "",
            (
                f"- 기존 `grounding_filter_effect.json`의 Hybrid+LLM-filter top-5: "
                f"harmful_rate={existing.get('harmful_rate')}, "
                f"queries_empty_grounding={existing.get('queries_empty_grounding')}, "
                f"avg_filled_slots={existing.get('avg_filled_slots')}"
            ),
        ])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    R.TOP_K = DEPTH
    queries = load_queries()
    corpus = load_corpus()
    qrels = load_qrels_3judge()
    rel_map = load_rel_map()
    self_doc = {q["query_id"]: "CASE-" + str(q.get("source_id", "")).strip() for q in queries}
    case_map = build_case_map(corpus)

    print("[1] sidecar query signals...")
    query_signals = {
        q["query_id"]: build_signals(q["query"], category=q.get("category", ""), source=q.get("source", ""))
        for q in queries
    }

    print("[2] BM25...")
    bm25 = run_bm25(queries, corpus)
    print("[3] Dense...")
    dense = run_dense(queries)
    print("[4] Hybrid RRF...")
    hybrid = rrf([bm25, dense], k=RRF_K)

    candidate_cases = {rec.docid for recs in hybrid.values() for rec in recs}
    print(f"[5] Chroma metadata doc signals... ({len(candidate_cases)} cases)")
    chroma_signals = load_chroma_signal_map("civil_cases_v1")
    doc_signals, signal_report = build_candidate_doc_signals(candidate_cases, case_map, chroma_signals)

    print("[6] metadata soft rerank...")
    hybrid_meta = apply_metadata_rerank(hybrid, query_signals, doc_signals)

    hybrid_metrics = metrics_for(hybrid, qrels, self_doc)
    hybrid_meta_metrics = metrics_for(hybrid_meta, qrels, self_doc)
    delta = {key: round(get(hybrid_meta_metrics, key) - get(hybrid_metrics, key), 6) for key in METRIC_KEYS}

    print("[7] grounding breakdown...")
    grounding_hybrid = summarize_grounding_docs(top_docs_no_self(hybrid, self_doc, GROUNDING_K), rel_map)
    grounding_meta = summarize_grounding_docs(top_docs_no_self(hybrid_meta, self_doc, GROUNDING_K), rel_map)
    llm_cache = json.loads(LLM_CACHE.read_text(encoding="utf-8")) if LLM_CACHE.exists() else {}
    filtered_docs, cache_stats = apply_llm_filter_cache(hybrid_meta, self_doc, llm_cache)
    grounding_meta_filter = summarize_grounding_docs(filtered_docs, rel_map)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_set": "qrels_pooled_3judge, NO-self",
        "n_queries": len(queries),
        "depth": DEPTH,
        "rrf_k": RRF_K,
        "signals": {
            "query_signal_source": "deterministic_sidecar",
            "query_signal_reason": "evaluation query files do not contain PR #314 metadata fields",
            "query_signal_coverage": signal_coverage(query_signals),
            **signal_report,
        },
        "general_search": {
            "metrics": METRIC_KEYS,
            "systems": {
                "Hybrid": hybrid_metrics,
                "Hybrid+metadata_soft_rerank": hybrid_meta_metrics,
            },
            "delta": delta,
        },
        "grounding": {
            "top_k": GROUNDING_K,
            "llm_filter_pool": LLM_FILTER_POOL,
            "systems": {
                "Hybrid": grounding_hybrid,
                "Hybrid+metadata_soft_rerank": grounding_meta,
                "Hybrid+metadata_soft_rerank+LLM_filter_cache_projection": grounding_meta_filter,
            },
            "llm_cache": {"path": str(LLM_CACHE.relative_to(ROOT)), **cache_stats},
            "existing_hybrid_llm_filter_baseline": load_existing_llm_filter_baseline(),
        },
        "reliability": {
            "interpretation": "directional regression benchmark, not final production quality proof",
            "qrels_stats": qrels_stats(qrels),
            "strengths": [
                "3-judge median relevance labels",
                "NO-self evaluation removes source document shortcut",
                "Dense top-50 and BM25 top-50 fair pooling reduces pooling bias",
            ],
            "limits": [
                "Queries are still evaluation-set structured complaints, not fresh production held-out complaints",
                "query_signals are deterministic sidecar signals because eval queries do not contain PR #314 BE1 output",
                "qrels are top-50 pool based and spotcheck reports remaining long-tail incompleteness",
                "LLM filter numbers use cache projection and should be validated with live production filter runs",
                "No human gold-seed agreement or statistical significance test is included in this PR",
            ],
            "recommended_next_checks": [
                "Build a 50-100 pair human gold-seed set",
                "Run evaluation on real BE1 structured query_signals after BE1 pipeline is available for held-out complaints",
                "Add bootstrap confidence intervals or paired significance tests for metric deltas",
                "Track production/offline failure cases by issue type, legal reference, department, and rel0 cause",
            ],
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(report)

    print(f"[리포트] {OUT_JSON}")
    print(f"[요약] {OUT_MD}")


if __name__ == "__main__":
    main()

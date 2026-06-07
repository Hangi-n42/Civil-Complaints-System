"""강한 LLM으로 검색 qrels를 전수 감사한다.

기존 `qrels_pooled_3judge.tsv`를 덮어쓰지 않고, strong judge 점수와
기존 점수를 비교한 별도 qrels/리포트를 생성한다.

실행 예:
  # API 없이 동작 확인
  python scripts/audit_qrels_with_strong_llm.py --limit 20 --dry-run \
    --checkpoint /tmp/strong_audit.jsonl \
    --out-qrels /tmp/qrels_pooled_strong_audit.tsv \
    --out-summary-json /tmp/strong_audit_summary.json \
    --out-summary-md /tmp/strong_audit_summary.md \
    --out-disagreements /tmp/strong_audit_disagreements.csv

  # OpenAI-compatible Chat Completions API
  OPENAI_API_KEY=... STRONG_AUDIT_MODEL=gpt-4o \
    python scripts/audit_qrels_with_strong_llm.py --provider openai --resume

  # Tailscale 너머 Ollama
  OLLAMA_BASE_URL=http://100.71.35.78:11434 \
    python scripts/audit_qrels_with_strong_llm.py --provider ollama --model qwen2.5:14b --resume
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
REPORT_DIR = ROOT / "reports" / "retrieval" / "v3"

DEFAULT_QRELS = DATA_DIR / "qrels_pooled_3judge.tsv"
DEFAULT_QUERIES = DATA_DIR / "queries.jsonl"
DEFAULT_CORPUS = DATA_DIR / "corpus_meta.json"
DEFAULT_CHECKPOINT = DATA_DIR / "checkpoints" / "strong_audit.jsonl"
DEFAULT_OUT_QRELS = DATA_DIR / "qrels_pooled_strong_audit.tsv"
DEFAULT_SUMMARY_JSON = REPORT_DIR / "strong_audit_summary.json"
DEFAULT_SUMMARY_MD = REPORT_DIR / "strong_audit_summary.md"
DEFAULT_DISAGREEMENTS = REPORT_DIR / "strong_audit_disagreements.csv"

DEFAULT_OPENAI_BASE_URL = os.getenv("OPENAI_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions")
DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://100.71.35.78:11434")
DEFAULT_MODEL = os.getenv("STRONG_AUDIT_MODEL", "gpt-4o")

RUBRIC_PROMPT = """당신은 민원 RAG 검색 평가셋을 감사하는 강한 LLM 채점관입니다.
기준 민원(Query)과 과거 민원 사례(Chunk)를 읽고, Chunk가 Query의 답변 초안 생성 근거로 얼마나 안전하고 유용한지 0~2점으로 평가하세요.

[엄격한 점수 기준]
- 2점: 답변 초안에 거의 그대로 넣어도 안전한 근거입니다. 핵심 쟁점, 대상/요건, 적용 법령·제도·절차, 해결 방향이 거의 같습니다.
- 1점: 참고는 되지만 그대로 넣으면 위험합니다. 같은 분야/주제이거나 일부 쟁점은 같지만 대상, 요건, 절차, 처분 수위, 보상/단속/안내 목적 등이 달라 수정이 필요합니다.
- 0점: 답변 근거로 넣으면 잘못된 안내를 만들 수 있습니다. 표면 키워드만 같거나 담당기관, 법령, 절차, 해결 방법이 다릅니다.

[중요한 판정 원칙]
- "수정 후 활용 가능"은 기본적으로 1점입니다.
- 2점은 법령/제도/절차/대상/해결 방향이 거의 같을 때만 줍니다.
- 핵심 쟁점이 다르면 키워드가 같아도 0점입니다.
- 보상 절차와 단순 보수 조치, 공사장 소음과 오토바이 소음처럼 해결 주체/법령이 다르면 0점입니다.
- 경계가 모호하면 낮은 점수를 선택하세요.

반드시 JSON만 응답하세요.
형식:
{
  "score": 0|1|2,
  "reason": "판단 사유 1~2문장",
  "rubric_flags": ["same_issue"|"same_law_or_policy"|"same_procedure"|"same_department"|"needs_modification"|"dangerous_mismatch"]
}
"""


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate(value: str, max_chars: int) -> str:
    text = str(value or "")
    return text if len(text) <= max_chars else text[:max_chars] + "..."


def load_queries(path: Path) -> dict[str, str]:
    queries: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            row = json.loads(raw)
            queries[str(row["query_id"])] = str(row.get("query") or "")
    return queries


def load_corpus(path: Path) -> dict[str, str]:
    corpus: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for row in json.load(handle):
            case_id = str(row.get("case_id") or "").strip()
            if case_id and case_id not in corpus:
                corpus[case_id] = str(row.get("chunk_text") or "")
    return corpus


def load_qrels(path: Path) -> list[dict[str, Any]]:
    qrels: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for lineno, raw in enumerate(handle):
            parts = raw.rstrip("\n").split("\t")
            if lineno == 0 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) == 4:
                qid, _, docid, rel = parts
            elif len(parts) == 3:
                qid, docid, rel = parts
            else:
                continue
            qrels.append({"query_id": qid, "case_id": docid, "old_rel": int(rel)})
    return qrels


def load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            row = json.loads(raw)
            rows[f"{row['query_id']}::{row['case_id']}"] = row
    return rows


def append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise ValueError("JSON object not found")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("JSON root is not object")
    return parsed


def normalize_judgement(raw: str) -> tuple[int, str, list[str]]:
    parsed = extract_json_object(raw)
    score = int(parsed.get("score"))
    if score not in (0, 1, 2):
        raise ValueError(f"invalid score: {score}")
    reason = _clean_text(parsed.get("reason"))
    flags_raw = parsed.get("rubric_flags") or []
    flags = []
    if isinstance(flags_raw, list):
        flags = [_clean_text(item) for item in flags_raw if _clean_text(item)]
    return score, reason, flags


def build_prompt(query_text: str, chunk_text: str, *, max_chars: int) -> str:
    query = _truncate(query_text, max_chars)
    chunk = _truncate(chunk_text, max_chars)
    return f"{RUBRIC_PROMPT}\n\n[Query]\n{query}\n\n[Chunk]\n{chunk}"


def call_openai(prompt: str, *, model: str, base_url: str, timeout: int, retries: int) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for provider=openai")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    return _post_json(
        base_url,
        payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=timeout,
        retries=retries,
        response_extractor=lambda data: data["choices"][0]["message"]["content"],
    )


def call_ollama(prompt: str, *, model: str, base_url: str, timeout: int, retries: int) -> str:
    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 256, "num_ctx": 4096},
    }
    return _post_json(
        url,
        payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
        retries=retries,
        response_extractor=lambda data: data.get("response", ""),
    )


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: int,
    retries: int,
    response_extractor,
) -> str:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            return str(response_extractor(data))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries - 1:
                time.sleep(min(2**attempt, 8))
    raise RuntimeError(f"request failed after {retries} attempts: {last_error}")


def mock_judgement(query_id: str, case_id: str, old_rel: int) -> tuple[int, str, list[str]]:
    seed = sum(ord(ch) for ch in f"{query_id}::{case_id}")
    if old_rel == 2 and seed % 5 == 0:
        return 1, "mock: rel2 경계 케이스를 보수적으로 1점으로 낮춤", ["needs_modification"]
    if old_rel == 0 and seed % 11 == 0:
        return 1, "mock: 기존 rel0 중 일부 관련 후보를 발견한 것으로 처리", ["needs_modification"]
    return old_rel, "mock: 기존 라벨 유지", ["same_issue"] if old_rel >= 1 else ["dangerous_mismatch"]


def decide(old_rel: int, strong_rel: int | None) -> tuple[str, int]:
    if strong_rel is None:
        return "audit_failed", old_rel
    if old_rel == strong_rel:
        return "match", strong_rel
    if old_rel == 2 and strong_rel <= 1:
        return "rel2_downgrade_candidate", strong_rel
    if old_rel == 0 and strong_rel >= 1:
        return "missed_relevant_candidate", strong_rel
    return "needs_human_review", strong_rel


def audit_pair(
    row: dict[str, Any],
    *,
    queries: dict[str, str],
    corpus: dict[str, str],
    provider: str,
    model: str,
    base_url: str,
    max_chars: int,
    timeout: int,
    retries: int,
) -> dict[str, Any]:
    qid = row["query_id"]
    case_id = row["case_id"]
    old_rel = int(row["old_rel"])
    query_text = queries.get(qid, "")
    chunk_text = corpus.get(case_id, "")

    try:
        if not query_text or not chunk_text:
            raise ValueError("missing query or chunk text")
        if provider == "mock":
            strong_rel, reason, flags = mock_judgement(qid, case_id, old_rel)
        else:
            prompt = build_prompt(query_text, chunk_text, max_chars=max_chars)
            if provider == "openai":
                raw = call_openai(prompt, model=model, base_url=base_url, timeout=timeout, retries=retries)
            elif provider == "ollama":
                raw = call_ollama(prompt, model=model, base_url=base_url, timeout=timeout, retries=retries)
            else:
                raise ValueError(f"unsupported provider: {provider}")
            strong_rel, reason, flags = normalize_judgement(raw)
    except Exception as exc:  # noqa: BLE001
        strong_rel, reason, flags = None, f"audit_failed: {exc}", []

    decision, final_rel = decide(old_rel, strong_rel)
    return {
        "query_id": qid,
        "case_id": case_id,
        "old_rel": old_rel,
        "strong_rel": strong_rel,
        "final_rel": final_rel,
        "decision": decision,
        "reason": reason,
        "rubric_flags": flags,
    }


def write_qrels(path: Path, qrels: list[dict[str, Any]], audit_rows: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("query_id\t0\tchunk_id\trelevance\n")
        for row in qrels:
            key = f"{row['query_id']}::{row['case_id']}"
            audit = audit_rows.get(key)
            rel = int(audit["final_rel"]) if audit else int(row["old_rel"])
            handle.write(f"{row['query_id']}\t0\t{row['case_id']}\t{rel}\n")


def kappa_weighted(old_scores: list[int], new_scores: list[int]) -> float:
    labels = [0, 1, 2]
    n = len(old_scores)
    if n == 0:
        return 0.0
    observed = 0.0
    for old, new in zip(old_scores, new_scores):
        observed += abs(old - new) / 2
    observed /= n

    old_counts = Counter(old_scores)
    new_counts = Counter(new_scores)
    expected = 0.0
    for a in labels:
        for b in labels:
            expected += (old_counts[a] / n) * (new_counts[b] / n) * (abs(a - b) / 2)
    if expected == 0:
        return 1.0 if observed == 0 else 0.0
    return round(1 - observed / expected, 4)


def build_summary(qrels: list[dict[str, Any]], audit_rows: dict[str, dict[str, Any]], *, qrels_path: Path) -> dict[str, Any]:
    audited = list(audit_rows.values())
    old_rel = Counter(int(row["old_rel"]) for row in qrels)
    final_rel = Counter(int(audit_rows.get(f"{row['query_id']}::{row['case_id']}", row).get("final_rel", row["old_rel"])) for row in qrels)
    strong_valid = [row for row in audited if row.get("strong_rel") is not None]
    decisions = Counter(row["decision"] for row in audited)
    old_scores = [int(row["old_rel"]) for row in strong_valid]
    strong_scores = [int(row["strong_rel"]) for row in strong_valid]
    exact = sum(1 for a, b in zip(old_scores, strong_scores) if a == b)
    binary = sum(1 for a, b in zip(old_scores, strong_scores) if (a >= 1) == (b >= 1))

    return {
        "source_qrels": str(qrels_path.relative_to(ROOT)) if qrels_path.is_absolute() and ROOT in qrels_path.parents else str(qrels_path),
        "audited_pairs": len(audited),
        "valid_strong_scores": len(strong_valid),
        "total_qrels_pairs": len(qrels),
        "old_rel_distribution": {str(k): old_rel.get(k, 0) for k in [0, 1, 2]},
        "final_rel_distribution": {str(k): final_rel.get(k, 0) for k in [0, 1, 2]},
        "decision_distribution": dict(sorted(decisions.items())),
        "agreement": {
            "exact": round(exact / len(strong_valid), 4) if strong_valid else 0.0,
            "binary_rel_ge_1": round(binary / len(strong_valid), 4) if strong_valid else 0.0,
            "weighted_kappa_linear": kappa_weighted(old_scores, strong_scores),
        },
        "rel2_downgrade_candidates": decisions.get("rel2_downgrade_candidate", 0),
        "missed_relevant_candidates": decisions.get("missed_relevant_candidate", 0),
    }


def write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Strong LLM qrels 감사 요약",
        "",
        "## 결론",
        "",
        f"- 감사된 쌍: {summary['audited_pairs']} / {summary['total_qrels_pairs']}",
        f"- 유효 strong score: {summary['valid_strong_scores']}",
        f"- exact agreement: {summary['agreement']['exact']:.4f}",
        f"- binary agreement(rel>=1): {summary['agreement']['binary_rel_ge_1']:.4f}",
        f"- weighted kappa(linear): {summary['agreement']['weighted_kappa_linear']:.4f}",
        f"- rel2 downgrade 후보: {summary['rel2_downgrade_candidates']}",
        f"- missed relevant 후보: {summary['missed_relevant_candidates']}",
        "",
        "## 라벨 분포",
        "",
        "| 기준 | rel0 | rel1 | rel2 |",
        "| --- | ---: | ---: | ---: |",
        (
            f"| 기존 | {summary['old_rel_distribution']['0']} | "
            f"{summary['old_rel_distribution']['1']} | {summary['old_rel_distribution']['2']} |"
        ),
        (
            f"| strong-audit | {summary['final_rel_distribution']['0']} | "
            f"{summary['final_rel_distribution']['1']} | {summary['final_rel_distribution']['2']} |"
        ),
        "",
        "## 결정 분포",
        "",
    ]
    for key, value in summary["decision_distribution"].items():
        lines.append(f"- `{key}`: {value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_disagreements(
    path: Path,
    audit_rows: dict[str, dict[str, Any]],
    queries: dict[str, str],
    corpus: dict[str, str],
) -> None:
    rows = [row for row in audit_rows.values() if row["decision"] != "match"]
    rows.sort(key=lambda row: (row["decision"] != "rel2_downgrade_candidate", row["query_id"], row["case_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "decision",
                "query_id",
                "case_id",
                "old_rel",
                "strong_rel",
                "final_rel",
                "reason",
                "rubric_flags",
                "query_text",
                "chunk_text",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "decision": row["decision"],
                "query_id": row["query_id"],
                "case_id": row["case_id"],
                "old_rel": row["old_rel"],
                "strong_rel": row["strong_rel"],
                "final_rel": row["final_rel"],
                "reason": row["reason"],
                "rubric_flags": "|".join(row.get("rubric_flags") or []),
                "query_text": _truncate(queries.get(row["query_id"], ""), 300),
                "chunk_text": _truncate(corpus.get(row["case_id"], ""), 500),
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="강한 LLM 기반 qrels 감사")
    parser.add_argument("--provider", choices=["openai", "ollama", "mock"], default=os.getenv("STRONG_AUDIT_PROVIDER", "openai"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--out-qrels", type=Path, default=DEFAULT_OUT_QRELS)
    parser.add_argument("--out-summary-json", type=Path, default=DEFAULT_SUMMARY_JSON)
    parser.add_argument("--out-summary-md", type=Path, default=DEFAULT_SUMMARY_MD)
    parser.add_argument("--out-disagreements", type=Path, default=DEFAULT_DISAGREEMENTS)
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체")
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 mock judge로 출력 경로만 검증")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite-checkpoint", action="store_true")
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    if args.dry_run:
        args.provider = "mock"
    if args.provider == "ollama" and args.model == DEFAULT_MODEL and "STRONG_AUDIT_MODEL" not in os.environ:
        args.model = "qwen2.5:14b"

    if args.checkpoint.exists() and not args.resume and not args.overwrite_checkpoint:
        raise SystemExit(f"checkpoint exists: {args.checkpoint} (use --resume or --overwrite-checkpoint)")
    if args.overwrite_checkpoint and args.checkpoint.exists():
        args.checkpoint.unlink()

    queries = load_queries(args.queries)
    corpus = load_corpus(args.corpus)
    qrels = load_qrels(args.qrels)
    done = load_checkpoint(args.checkpoint) if args.resume else {}
    base_url = args.base_url
    if not base_url:
        base_url = DEFAULT_OPENAI_BASE_URL if args.provider == "openai" else DEFAULT_OLLAMA_BASE_URL

    remaining = [row for row in qrels if f"{row['query_id']}::{row['case_id']}" not in done]
    if args.limit:
        remaining = remaining[: args.limit]

    print(f"[audit] provider={args.provider} model={args.model} pairs={len(remaining)} resume={len(done)}")
    started = time.perf_counter()
    for index, row in enumerate(remaining, 1):
        audit = audit_pair(
            row,
            queries=queries,
            corpus=corpus,
            provider=args.provider,
            model=args.model,
            base_url=base_url,
            max_chars=args.max_chars,
            timeout=args.timeout,
            retries=args.retries,
        )
        key = f"{audit['query_id']}::{audit['case_id']}"
        done[key] = audit
        append_checkpoint(args.checkpoint, audit)
        if index % 10 == 0 or index == len(remaining):
            rate = index / max(0.001, time.perf_counter() - started)
            print(f"  {index}/{len(remaining)} {key} old={audit['old_rel']} strong={audit['strong_rel']} {audit['decision']} | {rate:.2f} pairs/s")

    write_qrels(args.out_qrels, qrels, done)
    summary = build_summary(qrels, done, qrels_path=args.qrels)
    args.out_summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary_md(args.out_summary_md, summary)
    write_disagreements(args.out_disagreements, done, queries, corpus)

    print(f"[qrels] {args.out_qrels}")
    print(f"[summary] {args.out_summary_json}")
    print(f"[summary-md] {args.out_summary_md}")
    print(f"[disagreements] {args.out_disagreements}")


if __name__ == "__main__":
    main()

"""
qrels 재라벨링 스크립트 (#260)

공식 기준(docs/60_specs/retrieval_relevance_definition.md)의 0~2 척도를
프롬프트에 그대로 적용하여 qrels를 재라벨링합니다.

모델:  exaone3.5:7.8b + gemma3:12b
집계:  floor(평균) — 두 모델 모두 2점이어야 rel=2
체크포인트: 5쌍마다 저장

실행:
  python scripts/relabel_new_qrels_v3.py [--resume] [--target {new,old,all}] [--overwrite]
  --target new      신규 쿼리(Q-0051+) 처리 (기본값)
  --target old      기존 쿼리(Q-0001~Q-0050) 처리
  --target all      전체 처리
  --overwrite       LLM 점수로 직접 덮어쓰기 (기존 rel 보존 안 함)
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from collections import defaultdict
from math import floor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "evaluation" / "v3"
QRELS_PATH = DATA_DIR / "qrels.tsv"
QUERIES_PATH = DATA_DIR / "queries.jsonl"
CORPUS_PATH = DATA_DIR / "corpus_meta.json"
CHECKPOINT_PATH = DATA_DIR / "relabel_checkpoint.json"
CHECKPOINT_OLD_PATH = DATA_DIR / "relabel_checkpoint_old.json"
OLLAMA_URL = "http://localhost:11434/api/generate"

LABEL_MODELS = ["exaone3.5:7.8b", "gemma3:12b"]
CHECKPOINT_EVERY = 5
NEW_QID_MIN = 51  # Q-0051 이상이 신규

# ── 공식 기준 프롬프트 (retrieval_relevance_definition.md 0~2 척도) ─────────
SYSTEM_PROMPT = """당신은 민원 검색 관련성 평가 전문가입니다.
기준 민원(Query)과 과거 민원 사례(Chunk)를 읽고, Chunk가 Query 답변 작성에 얼마나 유용한지 0~2점으로 평가하세요.

[채점 기준 — 반드시 이 기준만 사용하세요]
- 2점 (Perfect): 기준 민원과 과거 민원의 핵심 쟁점(문제 상황)이 동일하고, 적용되는 법령/제도/해결책이 같음.
  과거 사례의 답변(조치 내용)을 현재 민원 답변에 거의 그대로 인용할 수 있는 경우.
- 1점 (Partial): 두 민원의 카테고리/주제는 같고 쟁점이 일부 일치하지만, 세부 상황(대상, 요건 등)이 달라 그대로 인용할 수는 없음.
  답변의 방향성을 잡거나 일부 규정을 참고하는 데 도움이 되는 경우.
- 0점 (Irrelevant): 표면적인 단어/키워드만 겹칠 뿐 실제 쟁점이나 행정 절차가 달라,
  답변 작성 시 컨텍스트로 주입하면 오히려 잘못된 안내(할루시네이션)를 유발할 수 있는 경우.

[판단 원칙]
- 행정 분야 -> 법령 -> 담당부서 -> 해결방법 순서로 일치 여부를 검토하세요.
- 핵심 쟁점이 다르면 표면적 키워드가 같아도 0점입니다.
- 경계가 모호하면 낮은 점수를 선택하세요.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 금지):
{"score": <0|1|2>, "reason": "<판단 사유 1~2문장>"}"""


def _is_new(qid: str) -> bool:
    m = re.search(r"\d+", qid)
    return int(m.group()) >= NEW_QID_MIN if m else False


def _qid_num(qid: str) -> int:
    m = re.search(r"\d+", qid)
    return int(m.group()) if m else 0


# ── 데이터 로딩 ───────────────────────────────────────────────────────────────

def load_queries() -> dict[str, str]:
    """qid -> query_text"""
    result = {}
    with QUERIES_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                result[obj["query_id"]] = obj["query"]
    return result


def load_corpus() -> dict[str, str]:
    """case_id -> chunk_text (case당 첫 번째 청크 사용)"""
    result = {}
    with CORPUS_PATH.open(encoding="utf-8") as f:
        for doc in json.load(f):
            cid = doc.get("case_id", "")
            if cid and cid not in result:
                result[cid] = doc.get("chunk_text", "")
    return result


def load_qrel_pairs(target: str = "new") -> list[tuple[str, str, int]]:
    """qrels.tsv에서 대상 쿼리 쌍 로드: [(qid, docid, current_rel), ...]
    target: 'new'(Q-0051+), 'old'(Q-0001~Q-0050), 'all'(전체)
    """
    pairs = []
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            parts = line.strip().split("\t")
            if i == 0 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) == 4:
                qid, _, docid, rel = parts
            elif len(parts) == 3:
                qid, docid, rel = parts
            else:
                continue
            n = _qid_num(qid)
            if target == "new" and n < NEW_QID_MIN:
                continue
            if target == "old" and n >= NEW_QID_MIN:
                continue
            pairs.append((qid, docid, int(rel)))
    return pairs


# ── LLM 호출 ──────────────────────────────────────────────────────────────────

def _call_ollama(model: str, prompt: str, timeout: int = 60) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 128},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("response", "")


def _extract_score(raw: str) -> int | None:
    """응답에서 0~2 정수 점수를 추출. 실패 시 None."""
    # 1차: JSON 파싱
    try:
        parsed = json.loads(raw.strip())
        s = int(round(float(parsed["score"])))
        if s in (0, 1, 2):
            return s
    except Exception:
        pass
    # 2차: JSON 블록 추출
    m = re.search(r'\{[^{}]*"score"\s*:\s*([012])[^{}]*\}', raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            s = int(round(float(parsed["score"])))
            if s in (0, 1, 2):
                return s
        except Exception:
            pass
    # 3차: score 숫자만
    m = re.search(r'"score"\s*:\s*([012])', raw)
    if m:
        return int(m.group(1))
    # 4차: 응답 내 단독 숫자
    m = re.search(r'\b([012])\b', raw[:50])
    if m:
        return int(m.group(1))
    return None


def label_pair(query_text: str, chunk_text: str, max_chars: int = 600) -> dict[str, int | None]:
    """두 모델로 (query, chunk) 쌍을 라벨링. {model: score}"""
    q = query_text[:max_chars].replace("\n", " / ")
    c = chunk_text[:max_chars]
    prompt = f"{SYSTEM_PROMPT}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"
    scores = {}
    for model in LABEL_MODELS:
        try:
            raw = _call_ollama(model, prompt)
            scores[model] = _extract_score(raw)
        except Exception as e:
            print(f"    [{model}] 오류: {e}")
            scores[model] = None
    return scores


def aggregate_scores(scores: dict[str, int | None]) -> int:
    """floor(평균). 유효 점수 없으면 0 반환."""
    valid = [v for v in scores.values() if v is not None]
    if not valid:
        return 0
    return floor(sum(valid) / len(valid))


# ── 체크포인트 ─────────────────────────────────────────────────────────────────

def load_checkpoint(target: str = "new") -> dict[str, int]:
    path = CHECKPOINT_OLD_PATH if target == "old" else CHECKPOINT_PATH
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_checkpoint(done: dict[str, int], target: str = "new") -> None:
    path = CHECKPOINT_OLD_PATH if target == "old" else CHECKPOINT_PATH
    path.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")


# ── qrels.tsv 업데이트 ────────────────────────────────────────────────────────

def update_qrels(new_labels: dict[str, int], overwrite: bool = False) -> None:
    """new_labels 로 qrels.tsv 갱신.
    overwrite=False: max(기존, 새) — 업그레이드 전용
    overwrite=True:  LLM 점수로 직접 덮어쓰기 (기존 rel 하향 허용)
    """
    lines_out = []
    updated = changed = 0
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        header = None
        for i, line in enumerate(f):
            raw = line.rstrip("\n")
            parts = raw.split("\t")
            if i == 0:
                header = raw
                lines_out.append(raw)
                continue
            if len(parts) == 4:
                qid, zero, docid, old_rel = parts
            elif len(parts) == 3:
                qid, docid, old_rel = parts
                zero = "0"
            else:
                lines_out.append(raw)
                continue
            key = f"{qid}::{docid}"
            if key in new_labels:
                merged = new_labels[key] if overwrite else max(int(old_rel), new_labels[key])
                lines_out.append(f"{qid}\t{zero}\t{docid}\t{merged}")
                updated += 1
                if merged != int(old_rel):
                    changed += 1
            else:
                lines_out.append(raw)
    QRELS_PATH.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    strategy = "덮어쓰기" if overwrite else "업그레이드"
    print(f"[OK] qrels.tsv 업데이트: {updated}건 반영, {changed}건 변경 ({strategy})")


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="체크포인트에서 재개")
    parser.add_argument("--max-pairs", type=int, default=0,
                        help="이번 실행에서 처리할 최대 쌍 수 (0=제한없음)")
    parser.add_argument("--target", choices=["new", "old", "all"], default="new",
                        help="처리 대상: new(Q-0051+), old(Q-0001~Q-0050), all(전체)")
    parser.add_argument("--overwrite", action="store_true",
                        help="LLM 점수로 직접 덮어쓰기 (기존 rel 하향 허용)")
    args = parser.parse_args()

    target_label = {"new": "신규(Q-0051+)", "old": "기존(Q-0001~Q-0050)", "all": "전체"}[args.target]
    strategy_label = "덮어쓰기" if args.overwrite else "업그레이드 전용"

    print("=" * 60)
    print(f"qrels 재라벨링 - {target_label}")
    print(f"모델: {', '.join(LABEL_MODELS)}")
    print(f"척도: 0~2 (공식 retrieval_relevance_definition.md 기준)")
    print(f"전략: {strategy_label}")
    print("=" * 60)

    queries = load_queries()
    corpus = load_corpus()
    pairs = load_qrel_pairs(args.target)
    n_queries = len({qid for qid, _, _ in pairs})
    print(f"\n전체 대상 쌍: {len(pairs)}건 ({n_queries}개 쿼리)")

    done = load_checkpoint(args.target) if args.resume else {}
    if done:
        print(f"체크포인트 로드: {len(done)}건 완료, 재개합니다.")

    todo = [(qid, docid, rel) for qid, docid, rel in pairs
            if f"{qid}::{docid}" not in done]
    if args.max_pairs > 0:
        todo = todo[:args.max_pairs]
    print(f"이번 실행 쌍: {len(todo)}건 (전체 남은 쌍: {len(pairs) - len(done)}건)\n")

    for idx, (qid, docid, old_rel) in enumerate(todo, 1):
        query_text = queries.get(qid, "")
        chunk_text = corpus.get(docid, "")
        if not query_text or not chunk_text:
            print(f"[{idx}/{len(todo)}] {qid}::{docid} — 텍스트 없음, skip")
            done[f"{qid}::{docid}"] = old_rel
            continue

        scores = label_pair(query_text, chunk_text)
        new_rel = aggregate_scores(scores)
        key = f"{qid}::{docid}"
        done[key] = new_rel

        score_str = " | ".join(
            f"{m.split(':')[0]}={v}" for m, v in scores.items()
        )
        marker = " *** rel 변경" if new_rel != old_rel else ""
        print(f"[{idx}/{len(todo)}] {qid}::{docid}  [{score_str}] -> {new_rel}{marker}")

        if idx % CHECKPOINT_EVERY == 0:
            save_checkpoint(done, args.target)
            print(f"  체크포인트 저장 ({len(done)}건)\n")

    save_checkpoint(done, args.target)

    # 통계
    old_rel2 = sum(1 for _, _, r in pairs if r == 2)
    new_rel2 = sum(1 for (qid, docid, _) in pairs
                   if done.get(f"{qid}::{docid}", 0) == 2)
    print(f"\n재라벨링 결과:")
    print(f"  rel=2 변화: {old_rel2}건 -> {new_rel2}건")
    if n_queries:
        print(f"  rel=2 평균: {old_rel2/n_queries:.1f}/쿼리 -> {new_rel2/n_queries:.1f}/쿼리")

    # qrels.tsv 반영
    update_qrels(done, overwrite=args.overwrite)
    print("\n완료. run_v3_evaluation.py 또는 run_v3_split_analysis.py로 재평가하세요.")


if __name__ == "__main__":
    main()

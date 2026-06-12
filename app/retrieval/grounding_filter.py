"""답변 초안 grounding용 LLM 관련성 필터 — 공유 코어 (#305).

eval 파이프라인 스테이지(LLMRelevanceFilterStage)와 프로덕션 RetrievalService.search()가
이 모듈을 공유한다(로직 단일화). 후보 텍스트를 LLM 관련성 루브릭(0/1/2)으로 채점하고,
임계값 미만(기본 rel0)을 제거한 뒤 점수 desc로 재정렬한다.

근거(#299/#303): 답변 grounding의 해로운(rel0) 선례를 27.8%→0.9%로 감소.

척도는 docs/60_specs/retrieval_relevance_definition.md, 평가 정답표(qrels)와 동일.
LLM: settings.OLLAMA_*(httpx async, temperature=0, format=json).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Awaitable, Callable, Sequence, TypeVar

import httpx

from app.core.config import settings

# 평가 정답표(qrels)를 만든 것과 동일한 0~2 관련성 루브릭. 점수만 받도록 reason은 생략.
RELEVANCE_RUBRIC = """당신은 민원 검색 관련성 평가 전문가입니다.
기준 민원(Query)과 과거 민원 사례(Chunk)를 읽고, Chunk가 Query 답변 작성에 얼마나 유용한지 0~2점으로 평가하세요.

[채점 기준 — 반드시 이 기준만 사용하세요]
- 2점 (Perfect): 핵심 쟁점이 동일하고 적용 법령/제도/해결책이 같음. 과거 답변을 거의 그대로 인용 가능.
- 1점 (Partial): 카테고리/주제는 같고 쟁점이 일부 일치하나 세부 상황이 달라 그대로 인용 불가. 방향 참고 수준.
- 0점 (Irrelevant): 표면 단어만 겹칠 뿐 실제 쟁점/절차가 달라, 컨텍스트로 주입하면 잘못된 안내(할루시네이션)를 유발.

[판단 원칙]
- 행정 분야 -> 법령 -> 담당부서 -> 해결방법 순으로 일치 여부를 검토.
- 핵심 쟁점이 다르면 표면 키워드가 같아도 0점. 경계가 모호하면 낮은 점수.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 금지):
{"score": <0|1|2>}"""

_SCORE_RE = re.compile(r'"?score"?\s*[:=]\s*([0-2])')
_DIGIT_RE = re.compile(r"\b([0-2])\b")

T = TypeVar("T")


def extract_score(raw: str) -> int | None:
    if not raw:
        return None
    m = _SCORE_RE.search(raw) or _DIGIT_RE.search(raw)
    return int(m.group(1)) if m else None


def build_prompt(query_text: str, doc_text: str, max_chars: int = 600) -> str:
    q = query_text[:max_chars].replace("\n", " / ")
    c = doc_text[:max_chars]
    return f"{RELEVANCE_RUBRIC}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"


def extract_scores(raw: str, expected_count: int) -> list[int] | None:
    """배치 응답의 점수 배열을 검증한다."""
    if not raw or expected_count <= 0:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    scores = parsed.get("scores") if isinstance(parsed, dict) else None
    if not isinstance(scores, list) or len(scores) != expected_count:
        return None
    if any(isinstance(score, bool) or not isinstance(score, int) or score not in (0, 1, 2) for score in scores):
        return None
    return scores


def build_batch_prompt(
    query_text: str,
    doc_texts: Sequence[str],
    max_chars: int = 400,
) -> str:
    """여러 후보를 한 번에 채점하는 짧은 프롬프트를 만든다."""
    query = query_text[:600].replace("\n", " / ")
    rubric = RELEVANCE_RUBRIC.rsplit("\n\n반드시 아래 JSON", maxsplit=1)[0]
    chunks = "\n\n".join(
        f"[후보 {index}]\n{text[:max_chars]}"
        for index, text in enumerate(doc_texts, start=1)
    )
    return (
        f"{rubric}\n\n"
        "아래 모든 후보를 순서대로 독립 평가하세요. "
        f"scores 배열에는 후보 수와 동일한 {len(doc_texts)}개 점수만 넣으세요.\n\n"
        f"기준 민원(Query):\n{query}\n\n{chunks}\n\n"
        f'응답 형식: {{"scores": [{", ".join("0|1|2" for _ in doc_texts)}]}}'
    )


async def score_relevance(
    query_text: str,
    doc_text: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int | None = None,
    max_chars: int = 600,
) -> int | None:
    """후보 1건을 0/1/2로 채점. 실패 시 None(상위에서 permissive 처리)."""
    payload = {
        "model": model or settings.OLLAMA_MODEL,
        "prompt": build_prompt(query_text, doc_text, max_chars),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 24, "num_ctx": 2048},
    }
    url = f"{(base_url or settings.OLLAMA_BASE_URL).rstrip('/')}/api/generate"
    try:
        async with httpx.AsyncClient(timeout=timeout or settings.OLLAMA_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                return None
            return extract_score(str(resp.json().get("response", "")))
    except (httpx.HTTPError, ValueError):
        return None


async def score_relevance_batch(
    query_text: str,
    doc_texts: Sequence[str],
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int | None = None,
    max_chars: int = 400,
) -> list[int] | None:
    """후보 여러 건을 단일 Ollama 호출로 채점한다.

    응답 오류 시 None을 반환하며 호출부가 기존 개별 판정으로 복귀한다.
    """
    docs = list(doc_texts)
    if not docs:
        return []
    count = len(docs)
    response_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["scores"],
        "properties": {
            "scores": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {"type": "integer", "minimum": 0, "maximum": 2},
            }
        },
    }
    payload = {
        "model": model or settings.OLLAMA_MODEL,
        "prompt": build_batch_prompt(query_text, docs, max_chars),
        "stream": False,
        "format": response_schema,
        "options": {
            "temperature": 0.0,
            "num_predict": max(24, count * 4 + 12),
            "num_ctx": 3072,
        },
    }
    url = f"{(base_url or settings.OLLAMA_BASE_URL).rstrip('/')}/api/generate"
    try:
        async with httpx.AsyncClient(timeout=timeout or settings.OLLAMA_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                return None
            return extract_scores(str(resp.json().get("response", "")), count)
    except (httpx.HTTPError, ValueError):
        return None


def filter_by_scores(
    items: Sequence[T],
    scores: Sequence[int | None],
    *,
    min_score: int = 1,
    top_k: int = 5,
) -> list[tuple[T, float]]:
    """이미 계산된 관련성 점수로 제거·재정렬한다."""
    kept: list[tuple[T, float, int]] = []
    for orig_rank, (item, score) in enumerate(zip(items, scores)):
        if score is None:
            kept.append((item, float(min_score) - 0.5, orig_rank))
        elif score >= min_score:
            kept.append((item, float(score), orig_rank))

    kept.sort(key=lambda value: (-value[1], value[2]))
    return [(item, score) for item, score, _ in kept[:top_k]]


async def filter_by_relevance(
    query_text: str,
    items: Sequence[T],
    *,
    get_text: Callable[[T], str],
    score_fn: Callable[[str, str], Awaitable[int | None]],
    min_score: int = 1,
    rerank_pool: int = 10,
    top_k: int = 5,
    max_concurrency: int = 4,
) -> list[tuple[T, float]]:
    """상위 rerank_pool 후보를 score_fn으로 채점→min_score 미만 제거→(점수desc, 원래순서)→top_k.

    - LLM 점수 None(실패)은 permissive 유지(제거하지 않음) → 일시 장애 시 무필터 graceful degradation.
    - 통과 0개면 빈 리스트(상위에서 "유사 사례 없음" 폴백).
    반환: [(item, score)] (score는 통과 항목의 관련성, 실패 항목은 min_score-0.5).
    """
    pool = list(items)[:rerank_pool]
    if not pool:
        return []
    sem = asyncio.Semaphore(max_concurrency)

    async def score_one(item: T) -> int | None:
        async with sem:
            return await score_fn(query_text, get_text(item))

    scores = await asyncio.gather(*(score_one(it) for it in pool))

    return filter_by_scores(pool, scores, min_score=min_score, top_k=top_k)

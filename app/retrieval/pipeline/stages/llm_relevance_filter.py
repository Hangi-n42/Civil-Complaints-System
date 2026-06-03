"""LLM 관련성 필터 단계 (#301).

상위 후보 각각을 LLM(관련성 루브릭)으로 0/1/2 채점하고, 임계값 미만(기본 rel0)을
제거한 뒤 점수 desc로 재정렬해 top_k를 남긴다. RAG grounding에서 해로운(rel0) 선례를
근거에서 배제하는 것이 목적.

근거(#299): Hybrid top-5의 23%가 rel0(주입 시 할루시네이션 유발). LLM 리랭커를 '재정렬'로
쓰면 미미(23→20%)했지만 '필터(0점 제거)'로 쓰니 해로움 23%→4%, 오염 쿼리 45%→14%.

설계:
  - 입력 후보 중 상위 ``rerank_pool``개만 채점(비용 절감), 나머지는 버림.
  - score >= ``min_score`` 만 통과 → (score desc, 원래 rank asc) 정렬 → top_k.
  - 통과 0개면 빈 결과 → 상위(generator)에서 "유사 사례 없음" 폴백.
  - LLM 호출 실패는 permissive(해당 후보 유지, 원래 순서 뒤로) → 일시 장애 시 무필터로 graceful degradation.
  - LLM: settings.OLLAMA_* (httpx async, temperature=0, format=json), 동시성 제한.

관련성 척도는 docs/60_specs/retrieval_relevance_definition.md 와 동일(평가 정답표와 일관).
"""

from __future__ import annotations

import asyncio
import re
import time

import httpx

from app.core.config import settings
from app.retrieval.pipeline.base import RetrievedDoc, StageInput, StageOutput
from app.retrieval.pipeline.stages.cross_encoder_rerank import _get_text

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


def _extract_score(raw: str) -> int | None:
    if not raw:
        return None
    m = _SCORE_RE.search(raw) or _DIGIT_RE.search(raw)
    return int(m.group(1)) if m else None


class LLMRelevanceFilterStage:
    """상위 후보를 LLM 관련성으로 채점 → 임계값 미만 제거 → 재정렬."""

    def __init__(
        self,
        *,
        name: str = "llm_relevance_filter",
        model: str | None = None,
        top_k: int = 5,
        min_score: int = 1,
        rerank_pool: int = 10,
        max_chars: int = 600,
        max_concurrency: int = 4,
    ) -> None:
        self.name = name
        self.model = model or settings.OLLAMA_MODEL
        self.top_k = top_k
        self.min_score = min_score
        self.rerank_pool = rerank_pool
        self.max_chars = max_chars
        self.max_concurrency = max_concurrency
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._timeout = settings.OLLAMA_TIMEOUT

    def _build_prompt(self, query_text: str, doc_text: str) -> str:
        q = query_text[: self.max_chars].replace("\n", " / ")
        c = doc_text[: self.max_chars]
        return f"{RELEVANCE_RUBRIC}\n\n기준 민원(Query):\n{q}\n\n과거 민원(Chunk):\n{c}"

    async def _score(self, query_text: str, doc_text: str) -> int | None:
        """후보 1건을 0/1/2로 채점. 실패 시 None(상위에서 permissive 처리)."""
        payload = {
            "model": self.model,
            "prompt": self._build_prompt(query_text, doc_text),
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_predict": 24, "num_ctx": 2048},
        }
        url = f"{self._base_url}/api/generate"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    return None
                return _extract_score(str(resp.json().get("response", "")))
        except (httpx.HTTPError, ValueError):
            return None

    async def run(self, stage_input: StageInput) -> StageOutput:
        candidates = list(stage_input.candidates)
        if not candidates:
            return StageOutput(stage_name=self.name, query=stage_input.query, candidates=[], latency_ms=0.0)

        pool = candidates[: self.rerank_pool]
        query_text = stage_input.query.text
        started_at = time.perf_counter()

        sem = asyncio.Semaphore(self.max_concurrency)

        async def score_one(doc: RetrievedDoc) -> int | None:
            async with sem:
                return await self._score(query_text, _get_text(doc))

        scores = await asyncio.gather(*(score_one(doc) for doc in pool))
        latency_ms = (time.perf_counter() - started_at) * 1000

        # 통과 규칙: 점수 None(LLM 실패)은 permissive 유지, 그 외는 min_score 이상만.
        kept: list[tuple[RetrievedDoc, float, int]] = []
        for orig_rank, (doc, score) in enumerate(zip(pool, scores)):
            if score is None:
                kept.append((doc, float(self.min_score) - 0.5, orig_rank))  # 판정 실패 → 양성 뒤
            elif score >= self.min_score:
                kept.append((doc, float(score), orig_rank))
            # score < min_score → 제거(해로운 선례 배제)

        kept.sort(key=lambda t: (-t[1], t[2]))  # 점수 desc, 동점은 원래 순서
        filtered = [
            RetrievedDoc(qid=doc.qid, docid=doc.docid, score=score, rank=rank, stage=self.name, metadata=doc.metadata)
            for rank, (doc, score, _) in enumerate(kept[: self.top_k], start=1)
        ]

        return StageOutput(
            stage_name=self.name,
            query=stage_input.query,
            candidates=filtered,
            latency_ms=latency_ms,
            metadata={"scored": len(pool), "kept": len(filtered)},
        )

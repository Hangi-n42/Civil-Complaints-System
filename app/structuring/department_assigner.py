"""담당부서/소관기관 후보 도출 (responsible_unit).

BE1 구조화 산출물 고도화 — 요청 #3.

설계 (벡터 핵심 + LLM 선택):
  1) busan_departments_master.json (배정용 정제본)의 업무(task) 단위 텍스트를
     bge-m3 로 임베딩해 전용 Chroma 컬렉션(busan_departments_v1)에 적재.
  2) 민원 질의를 임베딩해 의미상 가까운 업무 Top-K 를 검색.
  3) 업무 히트를 '부서' 단위로 집계 → confidence(유사도 기반 휴리스틱) + evidence 산출.
     부서명은 항상 컬렉션(=마스터 JSON)에 실재하는 정확한 부산시청 부서명 → 환각 0.
  4) (선택) LLM 재랭킹: 검색된 후보 집합 '안에서만' 선택/근거 보강.
     출력은 사후검증으로 후보 밖 이름·범위 초과 confidence 를 폐기.

주의:
  - confidence 는 코사인 유사도에서 유도한 '검증되지 않은' 점수다.
    민원→부서 정답셋이 없으므로 보정(calibration)된 확률이 아니다. BE2 는 상대값으로만 사용.
  - 무거운 의존성(chromadb / sentence_transformers / httpx / settings)은
    메서드 내부에서 지연 임포트한다. 모듈 임포트만으로 모델이 로드되지 않는다.
  - 순수 함수(extract_key_terms / aggregate_candidates / validate_llm_units)는
    모델·네트워크 없이 단위 테스트 가능하다.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.structuring.enrichment import FACILITY_KEYWORDS, LEGAL_REF_LEXICON, OBJECT_LEXICON

# ── 상수 ─────────────────────────────────────────────────────────────────
COLLECTION_NAME = "busan_departments_v1"
MASTER_FILENAME = "busan_departments_master.json"

# 다중 히트 1건당 confidence 가산치와 가산 상한(휴리스틱).
_MULTIHIT_BONUS = 0.02
_MAX_BONUS_HITS = 5
_CONF_CEILING = 0.99

# 키워드 추출 시 제거할 일반어(검색 신호가 약한 행정 상투어).
_STOPWORDS = {
    "신청", "문의", "절차", "관련", "사항", "경우", "등", "내용", "처리", "민원",
    "요청", "부탁", "안녕하세요", "감사합니다", "확인", "문제", "발생", "통해",
    "대한", "대해", "위해", "있습니다", "합니다", "해주세요", "주세요", "때문",
}

# 한글 2자 이상 또는 영숫자 2자 이상 토큰.
_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z0-9]{2,}")


# ── 순수 함수 (모델 불필요, 테스트 대상) ──────────────────────────────────
def _append_unique(target: List[str], values: List[str]) -> None:
    """빈 문자열과 중복을 제거하면서 순서를 보존해 단어를 추가한다."""
    for value in values:
        term = str(value or "").strip()
        if term and term not in target:
            target.append(term)


def _has_any_trigger(text: str, triggers: List[str]) -> bool:
    """부서/업무 원문 안에 같은 사전군의 트리거가 하나라도 있는지 확인한다."""
    return any(trigger and trigger in text for trigger in triggers)


def expand_department_task_text(department: str, task: str) -> str:
    """부서 업무를 인덱싱용 문서 텍스트로 확장한다.

    메타데이터의 표시용 task는 원문을 유지하고, 임베딩 대상 문서에만 부서명과
    기존 enrichment 사전의 도메인 동의어를 붙인다. 확장은 부서명/업무에 실제로
    등장한 트리거군으로 제한해 무관한 동의어가 모든 부서에 퍼지지 않게 한다.
    """
    base_terms: List[str] = []
    _append_unique(base_terms, [department, task])
    base_text = " ".join(base_terms)

    expansion_terms: List[str] = []
    for canonical, surfaces in OBJECT_LEXICON.items():
        group = [canonical, *surfaces]
        if _has_any_trigger(base_text, group):
            _append_unique(expansion_terms, group)

    for law_name, triggers in LEGAL_REF_LEXICON.items():
        group = [law_name, *triggers]
        if _has_any_trigger(base_text, group):
            _append_unique(expansion_terms, group)

    _append_unique(expansion_terms, [kw for kw in FACILITY_KEYWORDS if kw in base_text])
    return " ".join([*base_terms, *[term for term in expansion_terms if term not in base_terms]])


def extract_key_terms(text: str, limit: int = 12) -> List[str]:
    """질의/업무 텍스트에서 검색 신호가 되는 명사형 토큰을 추출한다.

    형태소 분석기가 아니라 경량 정규식 기반. evidence 겹침 계산과
    LLM 프롬프트 보조용으로 충분한 수준만 목표로 한다.
    """
    terms: List[str] = []
    seen = set()
    for tok in _TOKEN_RE.findall(text or ""):
        if tok in _STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
        if len(terms) >= limit:
            break
    return terms


def _evidence_terms(query_terms: List[str], task_text: str, max_terms: int = 3) -> List[str]:
    """질의 키워드 중 해당 업무 텍스트에 실제로 등장하는 것만 근거로 반환."""
    out: List[str] = []
    for t in query_terms:
        if t in task_text and t not in out:
            out.append(t)
        if len(out) >= max_terms:
            break
    return out


def aggregate_candidates(
    task_hits: List[Dict[str, Any]],
    query_terms: Optional[List[str]] = None,
    top_n: int = 3,
    min_confidence: float = 0.0,
) -> List[Dict[str, Any]]:
    """업무 단위 검색 히트를 부서 단위 responsible_unit 후보로 집계한다.

    Args:
        task_hits: [{"department": str, "task": str, "similarity": float in [0,1]}, ...]
                   similarity 는 코사인 유사도(1 - distance) 기준, 내림차순일 필요는 없음.
        query_terms: evidence 겹침 계산용 질의 키워드.
        top_n: 반환할 부서 수.
        min_confidence: 이 값 미만 후보는 제외.

    Returns:
        [{"name": 부서명, "confidence": float, "evidence": [근거 문구...]}, ...]
        confidence 내림차순. 부서명은 입력에 등장한 정확한 명칭.
    """
    query_terms = query_terms or []
    by_dept: Dict[str, Dict[str, Any]] = {}

    for hit in task_hits:
        dept = str(hit.get("department", "")).strip()
        task = str(hit.get("task", "")).strip()
        try:
            sim = float(hit.get("similarity", 0.0))
        except (TypeError, ValueError):
            sim = 0.0
        if not dept:
            continue
        sim = max(0.0, min(1.0, sim))

        slot = by_dept.setdefault(dept, {"best_sim": 0.0, "hits": 0, "best_task": "", "tasks": []})
        slot["hits"] += 1
        slot["tasks"].append((sim, task))
        if sim > slot["best_sim"]:
            slot["best_sim"] = sim
            slot["best_task"] = task

    results: List[Dict[str, Any]] = []
    for dept, slot in by_dept.items():
        extra = min(slot["hits"] - 1, _MAX_BONUS_HITS)
        confidence = min(_CONF_CEILING, slot["best_sim"] + _MULTIHIT_BONUS * extra)
        confidence = round(confidence, 4)
        if confidence < min_confidence:
            continue

        # 근거: 가장 유사한 업무 문구 + 질의와 겹치는 키워드
        evidence: List[str] = []
        if slot["best_task"]:
            evidence.append(slot["best_task"])
        evidence.extend(_evidence_terms(query_terms, slot["best_task"]))
        # 중복 제거(순서 보존)
        evidence = list(dict.fromkeys(evidence))

        results.append({
            "name": dept,
            "confidence": confidence,
            "evidence": evidence,
            "_hits": slot["hits"],  # 디버그용; 호출부에서 제거 가능
        })

    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results[:top_n]


def validate_llm_units(
    llm_units: Any,
    allowed_names: set,
) -> List[Dict[str, Any]]:
    """LLM 출력 responsible_unit 를 후보 집합 기준으로 사후검증한다.

    - name 이 allowed_names 에 없으면(환각) 폐기.
    - confidence 를 [0,1] 로 클램프, 누락 시 0.0.
    - evidence 는 리스트로 정규화.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(llm_units, list):
        return out
    seen = set()
    for u in llm_units:
        if not isinstance(u, dict):
            continue
        name = str(u.get("name", "")).strip()
        if name not in allowed_names or name in seen:
            continue
        seen.add(name)
        try:
            conf = float(u.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = round(max(0.0, min(1.0, conf)), 4)
        ev = u.get("evidence", [])
        if isinstance(ev, str):
            ev = [ev]
        elif not isinstance(ev, list):
            ev = []
        out.append({"name": name, "confidence": conf, "evidence": [str(e) for e in ev]})
    return out


def build_query_text(
    raw_text: str = "",
    entity_texts: Optional[List[str]] = None,
    key_terms: Optional[List[str]] = None,
) -> str:
    """BE1 산출물 요소들을 검색 질의 문자열로 합친다.

    entity_texts/key_terms 를 앞에 배치해 핵심 객체에 가중되도록 한다.
    """
    parts: List[str] = []
    if key_terms:
        parts.append(" ".join(key_terms))
    if entity_texts:
        parts.append(" ".join(entity_texts))
    if raw_text:
        parts.append(raw_text)
    return "\n".join(p for p in parts if p).strip()


# ── LLM 재랭킹 프롬프트 ───────────────────────────────────────────────────
_LLM_SYSTEM = """\
당신은 부산시청 민원 배정 보조 AI입니다.
[시민 민원]과 [후보 부서별 업무]를 비교해 책임 부서(responsible_unit)를 고르세요.

[규칙]
1. name 은 반드시 아래 [후보 부서] 목록에 있는 정확한 부서명만 사용합니다. 목록에 없는 이름은 절대 만들지 마세요.
2. confidence 는 민원과 부서 업무의 일치도를 0.0~1.0 실수로 매깁니다.
3. evidence 는 민원과 업무에서 일치하는 핵심어 2~3개를 배열로 넣습니다.
4. 아래 JSON 형식만 출력하고 다른 설명은 덧붙이지 마세요.

{"responsible_unit": [{"name": "...", "confidence": 0.0, "evidence": ["...", "..."]}]}\
"""


class DepartmentAssigner:
    """responsible_unit 도출기 (벡터 검색 핵심 + 선택적 LLM 재랭킹)."""

    def __init__(
        self,
        master_path: Optional[str] = None,
        persist_directory: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
        embedding_device: Optional[str] = None,
    ) -> None:
        from pathlib import Path
        from app.core.config import PROJECT_ROOT, settings

        self.master_path = Path(master_path) if master_path else (PROJECT_ROOT / "data" / "departments" / MASTER_FILENAME)
        self.persist_directory = persist_directory or settings.CHROMA_DB_PATH
        self.embedding_model_name = embedding_model_name or settings.EMBEDDING_MODEL
        self.embedding_device = embedding_device or settings.EMBEDDING_DEVICE
        self.min_confidence = float(getattr(settings, "RESPONSIBLE_UNIT_MIN_CONFIDENCE", 0.0))
        self._model = None
        self._client = None
        self._collection = None

    # ── 임베딩 / 컬렉션 (지연 로딩) ───────────────────────────────────────
    def _get_model(self):
        if self._model is None:
            device = str(self.embedding_device or "cpu").strip().lower()
            if device == "cuda":
                try:
                    import torch
                    if not torch.cuda.is_available():
                        device = "cpu"
                except Exception:
                    device = "cpu"
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.embedding_model_name, device=device)
        return self._model

    def _embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self._get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vecs.tolist() if hasattr(vecs, "tolist") else [list(v) for v in vecs]

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            from pathlib import Path
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_directory))
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── 인덱스 빌드 ──────────────────────────────────────────────────────
    def build_index(self, rebuild: bool = False) -> Dict[str, int]:
        """마스터 JSON 의 업무 텍스트를 임베딩해 컬렉션에 적재한다."""
        import json
        collection = self._get_collection()
        if rebuild:
            self._client.delete_collection(COLLECTION_NAME)
            self._collection = None
            collection = self._get_collection()
        elif collection.count() > 0:
            return {"departments": -1, "tasks": collection.count(), "skipped": 1}

        master = json.loads(self.master_path.read_text(encoding="utf-8"))
        ids, docs, metas = [], [], []
        for d_idx, dept in enumerate(master):
            name = dept["department"]
            for t_idx, task in enumerate(dept.get("tasks", [])):
                ids.append(f"{d_idx}_{t_idx}")
                docs.append(expand_department_task_text(name, task))
                metas.append({"department": name, "url": dept.get("url", ""), "task": task})

        # 배치 임베딩/적재
        BATCH = 128
        for i in range(0, len(docs), BATCH):
            chunk = docs[i:i + BATCH]
            collection.upsert(
                ids=ids[i:i + BATCH],
                documents=chunk,
                embeddings=self._embed(chunk),
                metadatas=metas[i:i + BATCH],
            )
        return {"departments": len(master), "tasks": len(docs), "skipped": 0}

    # ── 검색 + 집계 ──────────────────────────────────────────────────────
    def assign(
        self,
        query_text: str,
        top_k_tasks: int = 20,
        top_n_units: int = 3,
        min_confidence: Optional[float] = None,
        use_llm: bool = False,
    ) -> List[Dict[str, Any]]:
        """민원 질의 → responsible_unit 후보 리스트.

        min_confidence 미지정 시 설정값(RESPONSIBLE_UNIT_MIN_CONFIDENCE)을 적용한다.
        하한 미달이면 후보가 빈 배열로 폐기된다(자신 없는 출력 억제 = soft 폴백).
        """
        if min_confidence is None:
            min_confidence = self.min_confidence
        collection = self._get_collection()
        q_vec = self._embed([query_text])[0]
        res = collection.query(
            query_embeddings=[q_vec],
            n_results=top_k_tasks,
            include=["metadatas", "distances"],
        )
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        task_hits = [
            {
                "department": m.get("department", ""),
                "task": m.get("task", ""),
                "similarity": 1.0 - float(dist),  # cosine distance → similarity
            }
            for m, dist in zip(metas, dists)
        ]

        query_terms = extract_key_terms(query_text)
        candidates = aggregate_candidates(
            task_hits, query_terms=query_terms,
            top_n=top_n_units, min_confidence=min_confidence,
        )
        for c in candidates:
            c.pop("_hits", None)

        if use_llm and candidates:
            reranked = self._llm_rerank(query_text, candidates)
            if reranked:
                return reranked
        return candidates

    # ── 선택적 LLM 재랭킹 ────────────────────────────────────────────────
    def _llm_rerank(self, query_text: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """검색 후보 집합 안에서만 LLM 이 선택/근거 보강. 실패 시 빈 리스트(폴백)."""
        import json
        import httpx
        from app.core.config import settings

        allowed = {c["name"] for c in candidates}
        lines = []
        # 후보별 근거 업무 문구를 함께 제공 (name 은 후보 목록으로 고정)
        for c in candidates:
            ev_task = next((e for e in c.get("evidence", []) if len(e) > 6), "")
            lines.append(f"- 부서: {c['name']} | 업무: {ev_task}")
        user = (
            "[후보 부서별 업무]\n" + "\n".join(lines) +
            "\n\n[시민 민원]\n" + query_text[:1500]
        )
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_predict": 512},
        }
        try:
            with httpx.Client(timeout=settings.OLLAMA_TIMEOUT) as client:
                r = client.post(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat", json=payload)
                r.raise_for_status()
                raw = str(r.json().get("message", {}).get("content", "")).strip()
            parsed = json.loads(raw)
        except Exception:
            return []  # Ollama 불가/파싱 실패 → 벡터 결과 유지

        validated = validate_llm_units(parsed.get("responsible_unit"), allowed)
        return validated


# ── 싱글톤 ───────────────────────────────────────────────────────────────
_assigner: Optional[DepartmentAssigner] = None


def get_department_assigner() -> DepartmentAssigner:
    global _assigner
    if _assigner is None:
        _assigner = DepartmentAssigner()
    return _assigner

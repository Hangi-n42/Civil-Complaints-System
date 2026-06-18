"""구조화 서비스 (하이브리드: Rule NER + LLM 4요소 추출)

파이프라인:
  Stage 1 — Rule-based Entity Extractor
             ADMIN_UNIT / TIME / FACILITY / HAZARD / LOCATION 을 정규식·키워드로 추출.
             확실하게 추출 가능한 객관적 명사만 담당.

  Stage 2 — LLM Semantic Extractor (LLMSemanticExtractor)
             Ollama EXAONE 3.0 으로 4요소(observation/result/request/context) 추출.
             문맥 이해가 필요한 추상적 내용을 담당.

  Stage 3 — Result Merger + validate_schema()
             두 결과를 병합하고 evidence_span 을 탐색한 뒤 최종 스키마 검증.
"""

from __future__ import annotations

import time
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from app.core.config import settings
from app.core.exceptions import StructuringError
from app.core.logging import pipeline_logger
from app.structuring.enrichment import (
    FACILITY_KEYWORDS,
    build_key_terms,
    normalize_entity_texts,
)
from app.structuring.civil_category import classify_civil_category
from app.structuring.legal_dictionary import get_legal_ref_matcher
from app.structuring.llm_extractor import LLMSemanticExtractor
from app.structuring.merger import ResultMerger
from app.structuring.preprocessing import to_structuring_record
from app.structuring.structured_extractor import StructuredExtractor
from app.structuring.structured_merge import merge_structured
from app.structuring.verifier import make_ollama_verifier
from app.structuring.urgency.scorer import get_urgency_scorer
from app.structuring.schemas import RuleBasedNERResult


class StructuringService:
    """구조화 서비스 — Stage 1/2/3 오케스트레이터."""

    def __init__(self) -> None:
        self.logger = pipeline_logger
        self._kst = timezone(timedelta(hours=9))

        # ── Stage 1: NER 패턴 ─────────────────────────────────────────
        self._admin_unit_pattern = re.compile(
            r"((?:서울|부산|대구|인천|광주|대전|울산|세종|제주)(?:특별시|광역시|특별자치시|특별자치도|시)?"
            r"|(?:경기|강원|충청북|충청남|전라북|전라남|경상북|경상남)도"
            r"|(?:서울|부산|대구|인천|광주|대전|울산|세종|제주)\s*[가-힣]{1,10}(?:구|군|시))"
        )
        self._time_pattern = re.compile(
            r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일|\d{1,2}시|\d{4}[./-]\d{1,2}[./-]\d{1,2})"
        )
        # 동·읍·면·리·길 수준 위치명 (패턴 기반)
        # "가"(주격조사), "로"(방향조사) 제외 → 오추출 대폭 감소
        self._location_pattern = re.compile(
            r"[가-힣]{2,5}(?:동|읍|면|리)"
            r"|[가-힣]{2,8}(?:대로|번길|길)"
            r"|[가-힣]{1,3}(?:구|군)\s*[가-힣]{1,5}(?:동|읍|면|리)"
        )
        # 시설 체크리스트 고도화: enrichment.FACILITY_KEYWORDS (기존 8개 → 확장)
        self._facility_keywords = list(FACILITY_KEYWORDS)
        self._hazard_keywords = ["소음", "분진", "악취", "위험", "정체", "사고", "누수", "파손"]
        self._season_time_keywords = ["봄", "여름", "가을", "겨울", "매일", "주말", "평일", "야간", "새벽", "여름마다"]

        # ── LOCATION 비지명 오추출 필터 ────────────────────────────────
        # 행정구역 접미사(동·리·면)와 형태가 같은 어미·복합어를 걸러낸다.
        self._loc_nonplace_re = re.compile(
            # ~동: 노동·운동·활동·행동·이동·자동·시동·진동·충동·감동 등 복합명사
            r"(?:노|운|활|행|이|자|시|진|충|감|기|소|작|방|고)동$"
            # ~면: 조건어미 (~없으면·있으면·않으면 / ~되면·하면·이면·그러면 등)
            r"|(?:없|있|않)으면$"
            r"|(?:되|하|이|그러|아니|이러|저러)면$"
            r"|(?:으|야|려|지|시|내|다|라|니|해)면$"
            # ~면: 면(面) 복합어 — 지표면·바닥면·측면·전면·후면 등
            r"|(?:지표|바닥|측|전|후|상|하|좌|우|표|외|내|단|평|수|벽|마|노)면$"
            r"|시간면$"
            # ~리: 동사어미 드리다 / 복합어 관리·처리·정리·수리·소리·거리 등
            r"|드리$"
            r"|(?:관|처|정|수|소|거|다|모|기|나|마|하|오|아|이|사|주|가|보|청)리$"
        )
        # 소수 특정 오추출 리터럴 집합
        self._loc_literal_blocklist: set = {
            "콘크리",    # 콘크리트의 앞부분
            "아스팔",    # 아스팔트의 앞부분
            "이구동",    # 이구동성(異口同聲)의 일부
            "결정도면",  # 도시계획 결정도면
        }

        # ── FACILITY 복합어 오추출 방지 ────────────────────────────────
        # 법령·행정 문서 인용어에 키워드가 포함될 경우 단독 사용 여부를 확인한다.
        self._facility_compound_exclusion: Dict[str, re.Pattern] = {
            # 도로법·도로관리청·도로교통법·도로점용 등 법령 표현에서의 오추출 방지
            "도로": re.compile(
                r"도로(?:법|관리청|교통법|점용|구조령|노선|표지|설계기준|체계|계획|망|환경)"
            ),
        }

        # 엔티티 레이블 설정
        self._allowed_entity_labels = {"LOCATION", "TIME", "FACILITY", "HAZARD", "ADMIN_UNIT"}
        self._entity_label_normalize_map = {
            "TYPE": "HAZARD",
            "RISK": "HAZARD",
            "DATE": "TIME",
            "PLACE": "LOCATION",
            "AREA": "ADMIN_UNIT",
        }
        self._result_statuses = {"present", "pending", "insufficient"}
        self._priority_labels = {"매우급함", "급함", "보통"}
        self._priority_scale = ["보통", "급함", "매우급함"]
        self._category_enum = self._load_category_enum()
        self._province_names = {
            "경기도", "강원도", "충청북도", "충청남도", "전라북도",
            "전라남도", "경상북도", "경상남도", "제주도", "제주특별자치도",
        }
        self._metro_names = {
            "서울", "서울시", "서울특별시",
            "부산", "부산시", "부산광역시",
            "대구", "대구시", "대구광역시",
            "인천", "인천시", "인천광역시",
            "광주", "광주시", "광주광역시",
            "대전", "대전시", "대전광역시",
            "울산", "울산시", "울산광역시",
            "세종", "세종시", "세종특별자치시",
            "제주", "제주시", "제주특별자치도",
        }

        # ── Stage 2/3 컴포넌트 ────────────────────────────────────────
        self._llm_extractor = LLMSemanticExtractor(
            ollama_url=settings.OLLAMA_BASE_URL,
            model=settings.STRUCTURING_MODEL,
            timeout=settings.STRUCTURING_TIMEOUT,
            max_text_len=settings.STRUCTURING_MAX_TEXT_LEN,
        )
        self._merger = ResultMerger()
        # ① 제약 디코딩 추출기 (STRUCTURING_CONSTRAINED 플래그로 사용)
        self._structured_extractor = StructuredExtractor(
            ollama_url=settings.OLLAMA_BASE_URL,
            model=settings.STRUCTURING_MODEL,
            timeout=settings.STRUCTURING_TIMEOUT,
            max_text_len=settings.STRUCTURING_MAX_TEXT_LEN,
        )

    # ──────────────────────────────────────────────────────────────────
    # 입력 정규화 헬퍼
    # ──────────────────────────────────────────────────────────────────

    def _safe_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalize_created_at(self, created_at: str) -> str:
        value = (created_at or "").strip()
        if not value:
            return datetime.now(self._kst).isoformat()
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                parsed = datetime.strptime(value, fmt).replace(tzinfo=self._kst)
                return parsed.isoformat()
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=self._kst)
            else:
                parsed = parsed.astimezone(self._kst)
            return parsed.isoformat()
        except ValueError:
            return datetime.now(self._kst).isoformat()

    def _normalize_required(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
        if raw.get("consulting_content"):
            # 원천 consulting_content는 Q/A 또는 대화형일 수 있으므로 전처리 어댑터로 정규화한다.
            prepared = to_structuring_record(raw)
            prepared_metadata = (
                prepared.get("metadata", {}) if isinstance(prepared.get("metadata"), dict) else {}
            )
            raw = {**raw, **prepared}
            metadata = {**prepared_metadata, **metadata}

        case_id = str(raw.get("case_id") or raw.get("id") or "").strip()
        if not case_id:
            case_id = f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        source = str(raw.get("source") or metadata.get("source") or "unknown").strip() or "unknown"

        created_at = self._normalize_created_at(
            str(raw.get("created_at") or raw.get("submitted_at") or "").strip()
        )

        category = str(raw.get("category") or raw.get("consulting_category") or "unknown").strip() or "unknown"
        if category == "-":
            category = "unknown"

        region = str(raw.get("region") or metadata.get("region") or "unknown").strip() or "unknown"
        raw_text = str(raw.get("raw_text") or raw.get("text") or "").strip()

        return {
            "case_id": case_id,
            "source": source,
            "created_at": created_at,
            "category": category,
            "region": region,
            "raw_text": raw_text,
            "metadata": {
                "source_id": str(raw.get("source_id") or ""),
                "consulting_category": str(raw.get("consulting_category") or category),
                "consulting_turns": self._safe_int(raw.get("consulting_turns")),
                "consulting_length": self._safe_int(raw.get("consulting_length")),
                "client_gender": str(raw.get("client_gender") or ""),
                "client_age": str(raw.get("client_age") or ""),
                "source_file": str(metadata.get("source_file") or ""),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # 엔티티 레이블 헬퍼
    # ──────────────────────────────────────────────────────────────────

    async def _mask_structuring_text(self, text: str) -> str:
        """구조화 진입점에서 원문 개인정보 마스킹을 강제한다."""
        if not text:
            return ""

        from app.ingestion.service import get_ingestion_service

        ingestion_service = get_ingestion_service()
        cleaned = ingestion_service._clean_aihub_markup(text)
        return await ingestion_service.mask_pii(cleaned)

    def _normalize_entity_label(self, label: str) -> str:
        normalized = label.upper()
        return self._entity_label_normalize_map.get(normalized, normalized)

    def _sanitize_entities(self, entities: Any) -> Dict[str, Any]:
        errors: List[str] = []
        normalized_entities: List[Dict[str, str]] = []

        if not isinstance(entities, list):
            return {"entities": normalized_entities, "errors": ["invalid_type:entities"]}

        for idx, entity in enumerate(entities):
            if not isinstance(entity, dict):
                errors.append(f"invalid_entity_item_type:{idx}")
                continue

            raw_label = str(entity.get("label") or "").strip()
            text = str(entity.get("text") or "").strip()

            if not raw_label:
                errors.append(f"invalid_entity_label_at:{idx}")
                continue

            normalized_label = self._normalize_entity_label(raw_label)
            if normalized_label not in self._allowed_entity_labels:
                errors.append(f"invalid_entity_label:{raw_label.upper()}")
                continue

            normalized_entities.append({"label": normalized_label, "text": text})

        return {"entities": normalized_entities, "errors": errors}

    def _normalize_for_compare(self, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value or "")
        return re.sub(r"\s+", " ", normalized).strip()

    def _is_plausible_admin_unit(self, candidate: str) -> bool:
        value = (candidate or "").strip()
        if not value:
            return False
        compact = re.sub(r"\s+", "", value)
        if compact in self._province_names or compact in self._metro_names:
            return True
        if re.fullmatch(
            r"(?:서울|부산|대구|인천|광주|대전|울산|세종|제주)\s*[가-힣]{1,10}(?:구|군|시)",
            compact,
        ):
            return True
        return False

    def _pick_admin_unit(self, entities: Any, region: str) -> str:
        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                if str(entity.get("label")) != "ADMIN_UNIT":
                    continue
                text = str(entity.get("text") or "").strip()
                if text:
                    return text
        region_value = str(region or "").strip()
        if region_value and region_value != "unknown":
            return region_value
        return "unknown"

    def _load_category_enum(self) -> Dict[str, Dict[str, Any]]:
        config_path = Path(__file__).resolve().parents[2] / "configs" / "CATEGORY_ENUM.yaml"
        if not config_path.exists():
            self.logger.warning("CATEGORY_ENUM.yaml not found: %s", config_path)
            return {}

        try:
            with config_path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {}
        except Exception as exc:
            self.logger.warning("CATEGORY_ENUM.yaml load failed: %s", exc)
            return {}

        mapping: Dict[str, Dict[str, Any]] = {}
        for key, config in payload.items():
            if key in {"mapping_rules", "validation"}:
                continue
            if not isinstance(config, dict):
                continue

            names: set[str] = set()
            if key:
                names.add(str(key))
            korean_name = str(config.get("korean_name") or "").strip()
            if korean_name:
                names.add(korean_name)
            aliases = config.get("aliases", [])
            if isinstance(aliases, list):
                names.update(str(alias) for alias in aliases if alias)

            for name in names:
                mapping[name.lower()] = config

        return mapping

    def _priority_from_category(self, category: str) -> str:
        key = str(category or "").strip().lower()
        if not key:
            return "보통"

        config = self._category_enum.get(key)
        if not config:
            return "보통"

        sla = config.get("response_time_sla")
        if isinstance(sla, (int, float)):
            if sla <= 24:
                return "매우급함"
            if sla <= 72:
                return "급함"
            return "보통"

        level = str(config.get("priority") or "").lower()
        if level == "critical":
            return "매우급함"
        if level == "high":
            return "급함"
        return "보통"

    def _has_hazard_entity(self, entities: Any) -> bool:
        if not isinstance(entities, list):
            return False
        return any(isinstance(entity, dict) and entity.get("label") == "HAZARD" for entity in entities)

    def _compute_priority(self, category: str, entities: Any) -> str:
        base = self._priority_from_category(category)
        if not self._has_hazard_entity(entities):
            return base

        try:
            index = self._priority_scale.index(base)
        except ValueError:
            return base

        boosted = min(index + 1, len(self._priority_scale) - 1)
        return self._priority_scale[boosted]

    # ──────────────────────────────────────────────────────────────────
    # Stage 1: Rule-based Entity Extraction
    # ──────────────────────────────────────────────────────────────────

    async def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """ADMIN_UNIT / TIME / FACILITY / HAZARD / LOCATION 을 정규식·키워드로 추출한다."""
        try:
            self.logger.info("개체명 인식 시작: len=%d", len(text or ""))
            entities: List[Dict[str, str]] = []
            seen: set = set()

            # ADMIN_UNIT
            for m in self._admin_unit_pattern.finditer(text):
                token = m.group(1).strip()
                if not self._is_plausible_admin_unit(token):
                    continue
                ent = ("ADMIN_UNIT", token)
                if ent not in seen:
                    seen.add(ent)
                    entities.append({"label": "ADMIN_UNIT", "text": token})

            # TIME (날짜·시각 정규식)
            for m in self._time_pattern.finditer(text):
                ent = ("TIME", m.group(1))
                if ent not in seen:
                    seen.add(ent)
                    entities.append({"label": "TIME", "text": m.group(1)})

            # TIME (계절·주기 키워드)
            for kw in self._season_time_keywords:
                if kw in text:
                    ent = ("TIME", kw)
                    if ent not in seen:
                        seen.add(ent)
                        entities.append({"label": "TIME", "text": kw})

            # FACILITY
            for kw in self._facility_keywords:
                if kw not in text:
                    continue
                # 복합어 오추출 방지: 법령·기관명 표현에서만 등장하면 건너뜀
                excl = self._facility_compound_exclusion.get(kw)
                if excl:
                    cleaned = excl.sub("", text)
                    if kw not in cleaned:
                        continue  # 복합어에만 있고 단독 사용 없음
                ent = ("FACILITY", kw)
                if ent not in seen:
                    seen.add(ent)
                    entities.append({"label": "FACILITY", "text": kw})

            # HAZARD
            for kw in self._hazard_keywords:
                if kw in text:
                    ent = ("HAZARD", kw)
                    if ent not in seen:
                        seen.add(ent)
                        entities.append({"label": "HAZARD", "text": kw})

            # LOCATION (패턴 기반 — FACILITY/HAZARD 키워드와 중복 방지)
            facility_hazard_tokens = set(self._facility_keywords + self._hazard_keywords)
            for m in self._location_pattern.finditer(text):
                token = m.group(0).strip()
                # 비지명 패턴 제거 (조건어미·복합어·특정 리터럴)
                if self._loc_nonplace_re.search(token):
                    continue
                if token in self._loc_literal_blocklist:
                    continue
                if token in facility_hazard_tokens:
                    continue
                ent = ("LOCATION", token)
                if ent not in seen:
                    seen.add(ent)
                    entities.append({"label": "LOCATION", "text": token})

            return entities
        except Exception as exc:
            self.logger.error("개체명 인식 실패: %s", exc)
            raise StructuringError(f"개체명 인식 실패: {exc}") from exc

    # ──────────────────────────────────────────────────────────────────
    # Stage 3 보조: confidence
    # ──────────────────────────────────────────────────────────────────

    async def compute_confidence_score(self, data: Dict[str, Any]) -> float:
        """전체 구조화 신뢰도 점수를 계산한다 (0~1).

        가중치: observation 0.30, request 0.30, context 0.25, result 0.15.
        result.status="pending" 일 때 result 는 제외하고 재정규화.
        entities 개수에 따라 최대 0.05 보너스.
        """
        try:
            weights = {"observation": 0.30, "request": 0.30, "context": 0.25, "result": 0.15}
            result_status = str(data.get("result", {}).get("status") or "")
            keys = ["observation", "request", "context"] if result_status == "pending" else list(weights)

            total_weight = sum(weights[k] for k in keys)
            if total_weight <= 0:
                return 0.0

            score = sum(weights[k] * float(data.get(k, {}).get("confidence") or 0.0) for k in keys)
            score /= total_weight
            entity_bonus = min(len(data.get("entities", [])) * 0.01, 0.05)
            return max(0.0, min(1.0, score + entity_bonus))
        except Exception as exc:
            self.logger.error("신뢰도 점수 계산 실패: %s", exc)
            raise StructuringError(f"신뢰도 점수 계산 실패: {exc}") from exc

    # ──────────────────────────────────────────────────────────────────
    # Stage 3: 스키마 검증 (고도화)
    # ──────────────────────────────────────────────────────────────────

    async def validate_schema(
        self,
        data: Dict[str, Any],
        extraction_method: str = "hybrid",
    ) -> Dict[str, Any]:
        """구조화 결과의 스키마를 검증한다.

        extraction_method:
          "rule"   — Rule-based 추출. span 검증 엄격 (error).
                    "hybrid" — LLM + Rule 혼합. span 검증 완화.
                    "llm"    — LLM 단독. span 검증 완화.
                    "fallback" — LLM 실패로 빈 필드. span 검증 완화.
        """
        errors: List[str] = []
        lax_span = extraction_method in ("hybrid", "llm", "fallback")
        span_sources: Dict[str, str] = (
            data.get("extraction_meta", {}).get("span_sources", {}) or {}
        )

        try:
            self.logger.debug(
                "스키마 검증: case_id=%s, field_count=%d",
                data.get("case_id"),
                len(data),
            )

            # 필수 필드 존재 여부
            required = ["case_id", "source", "created_at", "raw_text",
                        "observation", "result", "request", "context", "entities", "admin_unit", "priority"]
            for key in required:
                if key not in data:
                    errors.append(f"missing:{key}")

            admin_unit = data.get("admin_unit")
            if not isinstance(admin_unit, str) or not admin_unit.strip():
                errors.append("invalid_admin_unit")

            priority = data.get("priority")
            if not isinstance(priority, str) or priority not in self._priority_labels:
                errors.append("invalid_priority")

            raw_text = str(data.get("raw_text") or "")
            text_len = len(raw_text)

            # 4요소 필드 검증
            for field_name in ("observation", "result", "request", "context"):
                field = data.get(field_name, {})
                if not isinstance(field, dict):
                    errors.append(f"invalid_type:{field_name}")
                    continue

                # confidence 범위
                conf = field.get("confidence")
                if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                    errors.append(f"invalid_confidence:{field_name}")

                # evidence_span 형식
                span = field.get("evidence_span")
                if not isinstance(span, list) or len(span) != 2:
                    errors.append(f"invalid_evidence_span:{field_name}")
                    continue
                if any(not isinstance(v, int) for v in span):
                    errors.append(f"invalid_evidence_span_type:{field_name}")
                    continue

                start, end = span

                # result.status pending/insufficient → span=[0,0] 정상
                if field_name == "result" and field.get("status") in ("pending", "insufficient"):
                    if span != [0, 0]:
                        errors.append(f"unexpected_span_for_status:{field.get('status')}")
                else:
                    if span == [0, 0]:
                        # inferred span (LLM이 위치를 특정하지 못한 경우)
                        src = span_sources.get(field_name)
                        if not (lax_span or src == "inferred") and field.get("text"):
                            errors.append(f"span_missing:{field_name}")
                    else:
                        # 범위 유효성
                        range_ok = (0 <= start < end <= text_len)
                        if not range_ok:
                            if not lax_span:
                                errors.append(f"invalid_evidence_span_range:{field_name}")
                        else:
                            # 텍스트 일치 검사
                            sliced = raw_text[start:end]
                            if self._normalize_for_compare(sliced) != self._normalize_for_compare(
                                str(field.get("text") or "")
                            ):
                                if not lax_span:
                                    errors.append(f"evidence_text_mismatch:{field_name}")

                # result.status 유효값
                if field_name == "result":
                    status = field.get("status")
                    if status is not None and status not in self._result_statuses:
                        errors.append("invalid_result_status")

                # 빈 텍스트 경고
                if not str(field.get("text") or "").strip():
                    errors.append(f"empty_field:{field_name}")

            # 엔티티 검증
            entity_result = self._sanitize_entities(data.get("entities", []))
            data["entities"] = entity_result["entities"]
            errors.extend(entity_result["errors"])

            # structured_by 유효값 검증 (신규 필드)
            if "structured_by" in data:
                allowed_methods = {"hybrid", "llm_only", "fallback", "rule", "constrained"}
                if data["structured_by"] not in allowed_methods:
                    errors.append("invalid_structured_by_value")

            # extraction_meta 검증 (신규 필드)
            meta = data.get("extraction_meta")
            if meta is not None:
                if not isinstance(meta.get("llm_latency_ms"), int):
                    errors.append("invalid_extraction_meta:llm_latency_ms")
                llm_count = meta.get("llm_non_null_count")
                if llm_count is not None and not (0 <= llm_count <= 4):
                    errors.append("invalid_extraction_meta:llm_non_null_count")

            return {"is_valid": len(errors) == 0, "errors": errors}

        except Exception as exc:
            self.logger.error("스키마 검증 실패: %s", exc)
            errors.append(f"exception:{exc}")
            return {"is_valid": False, "errors": errors}

    # ──────────────────────────────────────────────────────────────────
    # 종합 파이프라인
    # ──────────────────────────────────────────────────────────────────

    def _assign_responsible_unit(
        self,
        text: str,
        entity_texts: List[Dict[str, Any]],
        key_terms: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """담당부서 후보(responsible_unit)를 도출한다 (요청 #3).

        ENABLE_RESPONSIBLE_UNIT 플래그가 꺼져 있거나 임베딩 인덱스/모델이
        미가용이면 빈 리스트로 안전 폴백한다(기존 파이프라인 영향 없음).
        """
        if not getattr(settings, "ENABLE_RESPONSIBLE_UNIT", False):
            return []
        try:
            from app.structuring.department_assigner import (
                build_query_text,
                get_department_assigner,
            )

            query = build_query_text(
                raw_text=text,
                entity_texts=[e.get("text", "") for e in entity_texts if e.get("text")],
                key_terms=key_terms or [],
            )
            return get_department_assigner().assign(
                query, use_llm=getattr(settings, "RESPONSIBLE_UNIT_USE_LLM", False)
            )
        except Exception as exc:  # 인프라 미가용 시 구조화 자체는 계속 진행
            self.logger.warning("responsible_unit 도출 생략(인프라 미가용): %s", exc)
            return []

    def _category_urgency_floor(self, category: str) -> Optional[str]:
        """category SLA → 긴급도 floor(과소평가 방지). 매우급함→높음 / 급함→보통."""
        p = self._priority_from_category(category)
        return {"매우급함": "높음", "급함": "보통"}.get(p)

    def _score_urgency(self, text: str, category: str) -> Dict[str, Any]:
        """긴급도 산출(Track B). 모델 부재 시 규칙 폴백, 예외 시 안전 기본값."""
        try:
            return get_urgency_scorer().score(
                text, category=category or "",
                category_floor=self._category_urgency_floor(category or ""),
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("긴급도 산출 실패, 기본값: %s", exc)
            return {"level": "보통", "score": 0.0, "factors": {}, "evidence": [],
                    "override": None, "method": "error"}

    async def structure(self, record: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """민원 원문을 구조화된 JSON으로 변환한다.

        Returns:
            {
                case_id, source, created_at, category, region, raw_text, admin_unit, priority,
                observation, result, request, context,   # 4요소 (LLM)
                entities,                                # NER (Rule)
                metadata,
                structured_by,                           # "hybrid" | "constrained" | "fallback"
                extraction_meta,                         # LLM/NER 메타
                confidence_score,
                structured_at,
                validation,
            }
        """
        try:
            raw_record: Dict[str, Any] = {"text": record} if isinstance(record, str) else record
            normalized = self._normalize_required(raw_record)
            text = await self._mask_structuring_text(normalized["raw_text"])
            normalized["raw_text"] = text

            self.logger.info(
                "구조화 시작: case_id=%s, len=%d", normalized["case_id"], len(text)
            )

            # Stage 1: Rule NER
            ner_started = time.monotonic()
            entities = await self.extract_entities(text)
            ner_latency_ms = int((time.monotonic() - ner_started) * 1000)
            ner_result = RuleBasedNERResult(entities=entities, extraction_latency_ms=ner_latency_ms)

            # Stage 2/3: ① 제약 디코딩 경로(플래그) 또는 기존 자유 JSON 경로
            if getattr(settings, "STRUCTURING_CONSTRAINED", False):
                structured, llm_latency_ms = await self._structured_extractor.extract(text)
                verify_fn = None
                if getattr(settings, "ENABLE_SELF_VERIFY", False):
                    verify_fn = make_ollama_verifier(
                        settings.OLLAMA_BASE_URL, settings.STRUCTURING_MODEL,
                        timeout=settings.STRUCTURING_TIMEOUT,
                    )
                merged = merge_structured(
                    raw_text=text, ner_result=ner_result, structured=structured,
                    llm_latency_ms=llm_latency_ms, llm_model=settings.STRUCTURING_MODEL,
                    verify_fn=verify_fn,
                )
            else:
                # Stage 2: LLM 4요소 추출
                llm_output, llm_latency_ms = await self._llm_extractor.extract(text)
                # Stage 3: 병합
                merged = self._merger.merge(
                    raw_text=text,
                    ner_result=ner_result,
                    llm_output=llm_output,
                    llm_latency_ms=llm_latency_ms,
                    llm_model=settings.STRUCTURING_MODEL,
                )

            candidate: Dict[str, Any] = {
                "case_id": normalized["case_id"],
                "source": normalized["source"],
                "created_at": normalized["created_at"],
                "category": normalized["category"],
                "region": normalized["region"],
                "raw_text": text,
                "admin_unit": self._pick_admin_unit(entities, normalized["region"]),
                "priority": self._compute_priority(normalized["category"], entities),
                **merged,
                "metadata": normalized["metadata"],
            }

            # BE1 고도화 — 검색 신호 보강 필드 (규칙 #6: confidence + evidence 포함)
            candidate["entity_texts"] = normalize_entity_texts(entities, text)   # 요청 #1
            candidate["legal_refs"] = get_legal_ref_matcher().match(text)        # 요청 #2 (사전+도메인)
            candidate["key_terms"] = build_key_terms(                            # 요청 #5
                text,
                candidate["entity_texts"],
                candidate["legal_refs"],
            )
            candidate["responsible_unit"] = self._assign_responsible_unit(       # 요청 #3
                text, candidate["entity_texts"], candidate["key_terms"]
            )
            candidate["civil_category"] = classify_civil_category(              # 처리인 표시용 분야/세부태그
                text=text,
                category=normalized["category"],
                responsible_unit=candidate["responsible_unit"],
                entity_texts=candidate["entity_texts"],
                key_terms=candidate["key_terms"],
            )
            candidate["urgency"] = self._score_urgency(text, normalized["category"])  # 긴급도(Track B)

            # 신뢰도 점수
            candidate["confidence_score"] = await self.compute_confidence_score(candidate)
            candidate["structured_at"] = datetime.now(self._kst).isoformat()

            # 최종 스키마 검증
            candidate["validation"] = await self.validate_schema(
                candidate,
                extraction_method=candidate.get("structured_by", "hybrid"),
            )

            self.logger.info(
                "구조화 완료: case_id=%s (신뢰도=%.2f, valid=%s, structured_by=%s)",
                candidate["case_id"],
                candidate["confidence_score"],
                candidate["validation"]["is_valid"],
                candidate.get("structured_by"),
            )
            return candidate

        except Exception as exc:
            self.logger.error("구조화 실패: %s", exc)
            raise StructuringError(f"구조화 실패: {exc}") from exc


# 싱글톤
_structuring_service: Optional[StructuringService] = None


def get_structuring_service() -> StructuringService:
    global _structuring_service
    if _structuring_service is None:
        _structuring_service = StructuringService()
    return _structuring_service

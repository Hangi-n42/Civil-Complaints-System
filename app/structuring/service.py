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
from typing import Any, Dict, List, Optional, Union

from app.core.config import settings
from app.core.exceptions import StructuringError
from app.core.logging import pipeline_logger
from app.structuring.llm_extractor import LLMSemanticExtractor
from app.structuring.merger import ResultMerger
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
        # 동·읍·면·리·로·길 수준 위치명 (패턴 기반)
        self._location_pattern = re.compile(
            r"[가-힣]{2,5}(?:동|읍|면|리|가|로|길|대로|번길)"
            r"|[가-힣]{1,3}(?:구|군)\s*[가-힣]{1,5}(?:동|읍|면|리)"
        )
        self._facility_keywords = ["도로", "정류장", "가로등", "하수구", "교차로", "공사", "정수장", "놀이터"]
        self._hazard_keywords = ["소음", "분진", "악취", "위험", "정체", "사고", "누수", "파손"]
        self._season_time_keywords = ["봄", "여름", "가을", "겨울", "매일", "주말", "평일", "야간", "새벽", "여름마다"]

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
            "instructions": raw.get("instructions") if isinstance(raw.get("instructions"), list) else [],
        }

    # ──────────────────────────────────────────────────────────────────
    # 엔티티 레이블 헬퍼
    # ──────────────────────────────────────────────────────────────────

    def _normalize_entity_label(self, label: str) -> str:
        normalized = label.upper()
        return self._entity_label_normalize_map.get(normalized, normalized)

    def _sanitize_entities(self, entities: Any) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        normalized_entities: List[Dict[str, str]] = []

        if not isinstance(entities, list):
            return {"entities": normalized_entities, "errors": ["invalid_type:entities"], "warnings": warnings}

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

            if normalized_label != raw_label.upper():
                warnings.append(f"entity_label_normalized:{raw_label.upper()}->{normalized_label}")

            normalized_entities.append({"label": normalized_label, "text": text})

        return {"entities": normalized_entities, "errors": errors, "warnings": warnings}

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

    # ──────────────────────────────────────────────────────────────────
    # Stage 1: Rule-based Entity Extraction
    # ──────────────────────────────────────────────────────────────────

    async def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """ADMIN_UNIT / TIME / FACILITY / HAZARD / LOCATION 을 정규식·키워드로 추출한다."""
        try:
            self.logger.info("개체명 인식: %s...", text[:50])
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
                if kw in text:
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
    # Stage 3 보조: supervision / confidence
    # ──────────────────────────────────────────────────────────────────

    async def extract_supervision(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """라벨링 데이터 instructions 를 supervision 필드로 정규화한다."""
        result: Dict[str, Any] = {}
        instructions = raw.get("instructions", [])
        if not isinstance(instructions, list):
            return result

        qa_items: List[Dict[str, str]] = []
        for item in instructions:
            tuning_type = str(item.get("tuning_type", "")).strip()
            for row in item.get("data", []):
                normalized = {
                    "task_category": str(row.get("task_category", "")),
                    "instruction": str(row.get("instruction", "")),
                    "input": str(row.get("input", "")),
                    "output": str(row.get("output", "")),
                }
                if tuning_type == "분류":
                    result["classification"] = normalized
                elif tuning_type == "요약":
                    result["summary"] = normalized
                elif tuning_type == "질의응답":
                    qa_items.append({
                        "task_category": normalized["task_category"],
                        "instruction": normalized["instruction"],
                        "question": normalized["instruction"],
                        "answer": normalized["output"],
                    })
        if qa_items:
            result["qa"] = qa_items
        return result

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
          "hybrid" — LLM + Rule 혼합. span 불일치는 warning 으로 완화.
          "llm"    — LLM 단독. span 검증 동일하게 완화.
          "fallback" — LLM 실패로 빈 필드. span 검증 완화.
        """
        errors: List[str] = []
        warnings: List[str] = []
        lax_span = extraction_method in ("hybrid", "llm", "fallback")
        span_sources: Dict[str, str] = (
            data.get("extraction_meta", {}).get("span_sources", {}) or {}
        )

        try:
            self.logger.debug("스키마 검증: %s...", str(data)[:50])

            # 필수 필드 존재 여부
            required = ["case_id", "source", "created_at", "raw_text",
                        "observation", "result", "request", "context", "entities"]
            for key in required:
                if key not in data:
                    errors.append(f"missing:{key}")

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
                        warnings.append(f"unexpected_span_for_status:{field.get('status')}")
                else:
                    if span == [0, 0]:
                        # inferred span (LLM이 위치를 특정하지 못한 경우)
                        src = span_sources.get(field_name)
                        if lax_span or src == "inferred":
                            if field.get("text"):
                                warnings.append(f"span_inferred:{field_name}")
                        else:
                            if field.get("text"):
                                warnings.append(f"span_missing:{field_name}")
                    else:
                        # 범위 유효성
                        range_ok = (0 <= start < end <= text_len)
                        if not range_ok:
                            if lax_span:
                                warnings.append(f"invalid_evidence_span_range:{field_name}")
                            else:
                                errors.append(f"invalid_evidence_span_range:{field_name}")
                        else:
                            # 텍스트 일치 검사
                            sliced = raw_text[start:end]
                            if self._normalize_for_compare(sliced) != self._normalize_for_compare(
                                str(field.get("text") or "")
                            ):
                                if lax_span:
                                    warnings.append(f"evidence_text_mismatch:{field_name}")
                                else:
                                    errors.append(f"evidence_text_mismatch:{field_name}")

                # result.status 유효값
                if field_name == "result":
                    status = field.get("status")
                    if status is not None and status not in self._result_statuses:
                        errors.append("invalid_result_status")

                # 빈 텍스트 경고
                if not str(field.get("text") or "").strip():
                    warnings.append(f"empty_field:{field_name}")

            # 엔티티 검증
            entity_result = self._sanitize_entities(data.get("entities", []))
            data["entities"] = entity_result["entities"]
            errors.extend(entity_result["errors"])
            warnings.extend(entity_result["warnings"])

            # structured_by 유효값 검증 (신규 필드)
            if "structured_by" in data:
                allowed_methods = {"hybrid", "llm_only", "fallback", "rule"}
                if data["structured_by"] not in allowed_methods:
                    errors.append("invalid_structured_by_value")
                if data["structured_by"] == "fallback":
                    warnings.append("structuring_fallback_active")

            # extraction_meta 검증 (신규 필드)
            meta = data.get("extraction_meta")
            if meta is not None:
                if not isinstance(meta.get("llm_latency_ms"), int):
                    warnings.append("invalid_extraction_meta:llm_latency_ms")
                llm_count = meta.get("llm_non_null_count")
                if llm_count is not None and not (0 <= llm_count <= 4):
                    errors.append("invalid_extraction_meta:llm_non_null_count")

            if data.get("source") == "unknown":
                warnings.append("source_is_unknown")

            return {"is_valid": len(errors) == 0, "errors": errors, "warnings": warnings}

        except Exception as exc:
            self.logger.error("스키마 검증 실패: %s", exc)
            errors.append(f"exception:{exc}")
            return {"is_valid": False, "errors": errors, "warnings": warnings}

    # ──────────────────────────────────────────────────────────────────
    # 종합 파이프라인
    # ──────────────────────────────────────────────────────────────────

    async def structure(self, record: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """민원 원문을 구조화된 JSON으로 변환한다.

        Returns:
            {
                case_id, source, created_at, category, region, raw_text,
                observation, result, request, context,   # 4요소 (LLM)
                entities,                                # NER (Rule)
                supervision,                             # 라벨링 데이터 (선택)
                metadata,
                structured_by,                           # "hybrid" | "fallback"
                extraction_meta,                         # LLM/NER 메타
                confidence_score,
                structured_at,
                validation,
            }
        """
        try:
            raw_record: Dict[str, Any] = {"text": record} if isinstance(record, str) else record
            normalized = self._normalize_required(raw_record)
            text = normalized["raw_text"]

            self.logger.info(
                "구조화 시작: case_id=%s, len=%d", normalized["case_id"], len(text)
            )

            # Stage 1: Rule NER
            ner_started = time.monotonic()
            entities = await self.extract_entities(text)
            ner_latency_ms = int((time.monotonic() - ner_started) * 1000)
            ner_result = RuleBasedNERResult(entities=entities, extraction_latency_ms=ner_latency_ms)

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

            # supervision (라벨링 데이터)
            supervision = await self.extract_supervision(normalized)

            candidate: Dict[str, Any] = {
                "case_id": normalized["case_id"],
                "source": normalized["source"],
                "created_at": normalized["created_at"],
                "category": normalized["category"],
                "region": normalized["region"],
                "raw_text": text,
                **merged,
                "metadata": normalized["metadata"],
            }
            if supervision:
                candidate["supervision"] = supervision

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

"""
구조화 서비스

민원 원문을 구조화된 JSON으로 변환한다.
- 4요소 추출 (observation, result, request, context)
- NER (Named Entity Recognition)
- 스키마 합의안(case_id/source/created_at 포함) 기준 변환
"""

from typing import Dict, Any, List, Union
from datetime import datetime, timedelta, timezone
import re
from app.core.logging import pipeline_logger
from app.core.exceptions import StructuringError


class StructuringService:
    """구조화 서비스"""

    def __init__(self):
        """초기화"""
        self.logger = pipeline_logger
        self._kst = timezone(timedelta(hours=9))
        self._admin_unit_pattern = re.compile(
            r"((?:서울|부산|대구|인천|광주|대전|울산|세종|제주)(?:특별시|광역시|특별자치시|특별자치도|시)?"
            r"|(?:경기|강원|충청북|충청남|전라북|전라남|경상북|경상남)도"
            r"|(?:서울|부산|대구|인천|광주|대전|울산|세종|제주)\s*[가-힣]{1,10}(?:구|군|시))"
        )
        self._time_pattern = re.compile(r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일|\d{1,2}시|\d{4}[./-]\d{1,2}[./-]\d{1,2})")
        self._facility_keywords = ["도로", "정류장", "가로등", "하수구", "교차로", "공사", "정수장", "놀이터"]
        self._hazard_keywords = ["소음", "분진", "악취", "위험", "정체", "사고", "누수", "파손"]
        self._province_names = {
            "경기도",
            "강원도",
            "충청북도",
            "충청남도",
            "전라북도",
            "전라남도",
            "경상북도",
            "경상남도",
            "제주도",
            "제주특별자치도",
        }
        self._metro_names = {
            "서울",
            "서울시",
            "서울특별시",
            "부산",
            "부산시",
            "부산광역시",
            "대구",
            "대구시",
            "대구광역시",
            "인천",
            "인천시",
            "인천광역시",
            "광주",
            "광주시",
            "광주광역시",
            "대전",
            "대전시",
            "대전광역시",
            "울산",
            "울산시",
            "울산광역시",
            "세종",
            "세종시",
            "세종특별자치시",
            "제주",
            "제주시",
            "제주특별자치도",
        }
        self._allowed_entity_labels = {"LOCATION", "TIME", "FACILITY", "HAZARD", "ADMIN_UNIT"}
        self._entity_label_normalize_map = {
            "TYPE": "HAZARD",
            "RISK": "HAZARD",
            "DATE": "TIME",
            "PLACE": "LOCATION",
            "AREA": "ADMIN_UNIT",
        }

    def _is_plausible_admin_unit(self, candidate: str) -> bool:
        """행정단위로 해석 가능한 문자열인지 보수적으로 판별한다."""
        value = (candidate or "").strip()
        if not value:
            return False

        compact = re.sub(r"\s+", "", value)

        if compact in self._province_names or compact in self._metro_names:
            return True

        # "서울 강남구", "광주 북구" 형태를 허용한다.
        if re.fullmatch(
            r"(?:서울|부산|대구|인천|광주|대전|울산|세종|제주)\s*[가-힣]{1,10}(?:구|군|시)",
            compact,
        ):
            return True

        return False

    def _safe_int(self, value: Any) -> Union[int, None]:
        """문자열/숫자 값을 정수로 안전 변환한다."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalize_required(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """원천 데이터 필드를 합의된 내부 필드로 정규화한다."""
        metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}

        case_id = str(raw.get("case_id") or raw.get("id") or "").strip()
        if not case_id:
            case_id = f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        source = str(raw.get("source") or metadata.get("source") or "unknown").strip() or "unknown"

        created_at_raw = str(
            raw.get("created_at") or raw.get("submitted_at") or ""
        ).strip()
        created_at = self._normalize_created_at(created_at_raw)

        category = str(raw.get("category") or raw.get("consulting_category") or "unknown").strip() or "unknown"
        if category == "-":
            category = "unknown"

        region = str(raw.get("region") or metadata.get("region") or "unknown").strip() or "unknown"

        raw_text = str(raw.get("raw_text") or raw.get("text") or "").strip()

        normalized = {
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
        return normalized

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

    def _build_field(self, text: str, start: int, end: int, confidence: float) -> Dict[str, Any]:
        """4요소 공통 필드 객체 생성"""
        safe_text = (text or "").strip()
        if not safe_text:
            return {"text": "", "confidence": confidence, "evidence_span": [0, 0]}
        safe_start = max(0, start)
        safe_end = max(safe_start, end)
        return {
            "text": safe_text,
            "confidence": max(0.0, min(1.0, confidence)),
            "evidence_span": [safe_start, safe_end],
        }

    def _normalize_entity_label(self, label: str) -> str:
        """비표준 entity label을 표준 label로 변환한다."""
        normalized = label.upper()
        return self._entity_label_normalize_map.get(normalized, normalized)

    def _sanitize_entities(self, entities: Any) -> Dict[str, Any]:
        """entity 배열을 표준 label로 정규화하고, 미허용 값은 차단한다."""
        errors: List[str] = []
        warnings: List[str] = []
        normalized_entities: List[Dict[str, str]] = []

        if not isinstance(entities, list):
            return {
                "entities": normalized_entities,
                "errors": ["invalid_type:entities"],
                "warnings": warnings,
            }

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

        return {
            "entities": normalized_entities,
            "errors": errors,
            "warnings": warnings,
        }

    async def extract_four_elements(self, text: str) -> Dict[str, Dict[str, Any]]:
        """
        4요소(observation/result/request/context) 추출

        Args:
            text: 원본 텍스트

        Returns:
            {
                "observation": {...},
                "result": {...},
                "request": {...},
                "context": {...}
            }
        """
        try:
            self.logger.info(f"4요소 추출: {text[:50]}...")
            clean_text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            q_match = re.search(r"Q\s*:\s*(.+?)(?:\n\s*A\s*:|$)", text, flags=re.DOTALL)
            a_match = re.search(r"A\s*:\s*(.+)$", text, flags=re.DOTALL)

            question = (q_match.group(1).strip() if q_match else clean_text[:600].strip())
            answer = (a_match.group(1).strip() if a_match else "")

            sentences = [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n", question) if s.strip()]
            request_candidates = [
                s
                for s in sentences
                if re.search(r"요청|부탁|조치|개선|점검|정비|수리|바랍니다|해주시", s)
            ]

            obs_text = sentences[0] if sentences else question[:220]
            req_text = request_candidates[-1] if request_candidates else (sentences[-1] if sentences else question)
            res_text = answer[:220] if answer else "답변 본문 미제공"

            if "제목" in text:
                title_line = text.splitlines()[0][:140]
                ctx_text = title_line
            else:
                context_candidates = [
                    s
                    for s in sentences
                    if re.search(r"최근|지난|매일|주간|월간|년|월|일|시|구|동|읍|면|로|길", s)
                ]
                ctx_text = context_candidates[0] if context_candidates else clean_text[:140]

            obs_text = re.sub(r"^\s*(제목\s*[:：]\s*)", "", obs_text).strip()
            req_text = re.sub(r"^\s*(요청\s*[:：]\s*)", "", req_text).strip()
            ctx_text = re.sub(r"^\s*(제목\s*[:：]\s*)", "", ctx_text).strip()

            if not obs_text:
                obs_text = clean_text[:160]
            if not req_text:
                req_text = clean_text[-160:] if clean_text else "요청 내용 확인 필요"
            if not ctx_text:
                ctx_text = clean_text[:120]

            obs_start = text.find(obs_text) if obs_text else 0
            req_start = text.find(req_text) if req_text else 0
            res_start = text.find(res_text) if res_text and res_text != "답변 본문 미제공" else 0
            ctx_start = text.find(ctx_text) if ctx_text else 0

            return {
                "observation": self._build_field(obs_text, obs_start, obs_start + len(obs_text), 0.72),
                "result": self._build_field(res_text, res_start, res_start + len(res_text), 0.76),
                "request": self._build_field(req_text, req_start, req_start + len(req_text), 0.71),
                "context": self._build_field(ctx_text, ctx_start, ctx_start + len(ctx_text), 0.68),
            }
        except Exception as e:
            self.logger.error(f"4요소 추출 실패: {str(e)}")
            raise StructuringError(f"4요소 추출 실패: {str(e)}") from e

    async def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """
        개체명 인식 (NER)

        Args:
            text: 텍스트

        Returns:
            [{"label": "LOCATION", "text": "..."}, ...]
        """
        try:
            self.logger.info(f"개체명 인식: {text[:50]}...")
            entities: List[Dict[str, str]] = []
            seen = set()

            for m in self._admin_unit_pattern.finditer(text):
                token = m.group(1).strip()
                if not self._is_plausible_admin_unit(token):
                    continue
                ent = ("ADMIN_UNIT", token)
                if ent not in seen:
                    seen.add(ent)
                    entities.append({"label": ent[0], "text": ent[1]})

            for m in self._time_pattern.finditer(text):
                ent = ("TIME", m.group(1))
                if ent not in seen:
                    seen.add(ent)
                    entities.append({"label": ent[0], "text": ent[1]})

            for keyword in self._facility_keywords:
                if keyword in text:
                    ent = ("FACILITY", keyword)
                    if ent not in seen:
                        seen.add(ent)
                        entities.append({"label": ent[0], "text": ent[1]})

            for keyword in self._hazard_keywords:
                if keyword in text:
                    ent = ("HAZARD", keyword)
                    if ent not in seen:
                        seen.add(ent)
                        entities.append({"label": ent[0], "text": ent[1]})

            for loc_keyword in ["서울", "경기", "경상남도", "안양", "송파구", "풍납동"]:
                if loc_keyword in text:
                    ent = ("LOCATION", loc_keyword)
                    if ent not in seen:
                        seen.add(ent)
                        entities.append({"label": ent[0], "text": ent[1]})

            return entities
        except Exception as e:
            self.logger.error(f"개체명 인식 실패: {str(e)}")
            raise StructuringError(f"개체명 인식 실패: {str(e)}") from e

    async def validate_schema(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        스키마 검증

        Args:
            data: 구조화된 데이터

        Returns:
            {"is_valid": bool, "errors": List[str]}
        """
        errors: List[str] = []
        warnings: List[str] = []
        try:
            self.logger.debug(f"스키마 검증: {str(data)[:50]}...")
            required = [
                "case_id",
                "source",
                "created_at",
                "raw_text",
                "observation",
                "result",
                "request",
                "context",
                "entities",
            ]
            for key in required:
                if key not in data:
                    errors.append(f"missing:{key}")

            for field_name in ["observation", "result", "request", "context"]:
                field = data.get(field_name, {})
                if not isinstance(field, dict):
                    errors.append(f"invalid_type:{field_name}")
                    continue
                conf = field.get("confidence")
                if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                    errors.append(f"invalid_confidence:{field_name}")
                span = field.get("evidence_span")
                if not isinstance(span, list) or len(span) != 2:
                    errors.append(f"invalid_evidence_span:{field_name}")
                elif any(not isinstance(v, int) for v in span):
                    errors.append(f"invalid_evidence_span_type:{field_name}")

                text_value = str(field.get("text") or "").strip()
                if not text_value:
                    warnings.append(f"empty_field:{field_name}")

            entity_result = self._sanitize_entities(data.get("entities", []))
            data["entities"] = entity_result["entities"]
            errors.extend(entity_result["errors"])
            warnings.extend(entity_result["warnings"])

            if data.get("source") == "unknown":
                warnings.append("source_is_unknown")

            return {"is_valid": len(errors) == 0, "errors": errors, "warnings": warnings}
        except Exception as e:
            self.logger.error(f"스키마 검증 실패: {str(e)}")
            errors.append(f"exception:{str(e)}")
            return {"is_valid": False, "errors": errors, "warnings": warnings}

    async def extract_supervision(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """라벨링 데이터 instructions를 supervision 필드로 정규화한다."""
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
                    qa_items.append(
                        {
                            "task_category": normalized["task_category"],
                            "instruction": normalized["instruction"],
                            "question": normalized["instruction"],
                            "answer": normalized["output"],
                        }
                    )
        if qa_items:
            result["qa"] = qa_items
        return result

    async def compute_confidence_score(self, data: Dict[str, Any]) -> float:
        """
        신뢰도 점수 계산

        Args:
            data: 추출된 데이터

        Returns:
            신뢰도 점수 (0~1)
        """
        try:
            self.logger.debug("신뢰도 점수 계산")
            base = 0.55
            entity_bonus = min(len(data.get("entities", [])) * 0.03, 0.2)
            field_bonus = 0.0
            for key in ["observation", "result", "request", "context"]:
                if data.get(key, {}).get("text"):
                    field_bonus += 0.05
            return max(0.0, min(1.0, base + entity_bonus + field_bonus))
        except Exception as e:
            self.logger.error(f"신뢰도 점수 계산 실패: {str(e)}")
            raise StructuringError(f"신뢰도 점수 계산 실패: {str(e)}") from e

    async def structure(self, record: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        구조화 종합 파이프라인

        Args:
            record: 원본 텍스트 또는 원천 레코드 딕셔너리

        Returns:
            {
                "case_id": "...",
                "source": "...",
                "created_at": "...",
                "category": "...",
                "region": "...",
                "raw_text": "...",
                "observation": {...},
                "result": {...},
                "request": {...},
                "context": {...},
                "entities": [...],
                "supervision": {...},
                "metadata": {...},
                "structured_at": "2026-03-11T...",
                "validation": {"is_valid": true, "errors": []}
            }
        """
        try:
            if isinstance(record, str):
                raw_record: Dict[str, Any] = {"text": record}
            else:
                raw_record = record

            normalized = self._normalize_required(raw_record)
            text = normalized["raw_text"]

            self.logger.info(f"구조화 시작: case_id={normalized['case_id']}, len={len(text)}")

            # 4요소 추출
            four_elements = await self.extract_four_elements(text)

            # 개체명 인식
            entities = await self.extract_entities(text)

            # 라벨링 supervision 추출(있는 경우)
            supervision = await self.extract_supervision(normalized)

            candidate = {
                "case_id": normalized["case_id"],
                "source": normalized["source"],
                "created_at": normalized["created_at"],
                "category": normalized["category"],
                "region": normalized["region"],
                "raw_text": text,
                "observation": four_elements["observation"],
                "result": four_elements["result"],
                "request": four_elements["request"],
                "context": four_elements["context"],
                "entities": entities,
                "metadata": normalized["metadata"],
            }
            if supervision:
                candidate["supervision"] = supervision

            # 신뢰도 점수 계산
            confidence = await self.compute_confidence_score(candidate)

            # 결과 구성
            result = dict(candidate)
            result["confidence_score"] = confidence
            result["structured_at"] = datetime.now(self._kst).isoformat()

            # 스키마 검증
            result["validation"] = await self.validate_schema(result)

            self.logger.info(
                f"구조화 완료: case_id={result['case_id']} (신뢰도: {confidence:.2f}, valid={result['validation']['is_valid']})"
            )
            return result

        except Exception as e:
            self.logger.error(f"구조화 실패: {str(e)}")
            raise StructuringError(f"구조화 실패: {str(e)}") from e


# 싱글톤
_structuring_service = None


def get_structuring_service() -> StructuringService:
    """구조화 서비스 인스턴스 반환"""
    global _structuring_service
    if _structuring_service is None:
        _structuring_service = StructuringService()
    return _structuring_service

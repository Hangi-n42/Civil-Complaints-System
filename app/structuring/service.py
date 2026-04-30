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
import unicodedata
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
        self._season_time_keywords = ["봄", "여름", "가을", "겨울", "매일", "주말", "평일", "야간", "새벽", "여름마다"]
        self._observation_keywords = [
            "불법",
            "위반",
            "무단",
            "점거",
            "무단점용",
            "불법주차",
            "고장",
            "파손",
            "균열",
            "침하",
            "누수",
            "역류",
            "범람",
            "악취",
            "소음",
            "진동",
            "분진",
            "위험",
            "사고",
            "불편",
            "이용 불가",
            "통행 불편",
        ]
        self._request_keywords = [
            "요청",
            "요구",
            "건의",
            "조치",
            "시정",
            "개선",
            "보수",
            "정비",
            "복구",
            "철거",
            "교체",
            "설치",
            "보강",
            "점검",
            "단속",
            "계도",
            "행정처분",
            "과태료",
            "바랍니다",
            "부탁드립니다",
            "신속 처리",
            "조속한 처리",
            "해주시",
        ]
        self._context_keywords = [
            "년",
            "월",
            "일",
            "시",
            "최근",
            "지난",
            "매일",
            "상시",
            "지속",
            "반복",
            "재차",
            "기존",
            "이전",
            "신고",
            "민원",
            "시민",
            "주민",
            "시청",
            "구청",
            "도청",
            "하천",
            "산책로",
            "공장",
        ]
        self._result_keywords = [
            "답변",
            "회신",
            "안내",
            "처리 결과",
            "검토 결과",
            "조치 결과",
            "처리",
            "조치",
            "시행",
            "이행",
            "완료",
            "종결",
            "해소",
            "진행",
            "추진",
            "착수",
            "예정",
            "계획",
            "통보",
            "명령",
            "계고",
            "행정처분",
        ]
        self._request_pattern = re.compile(
            r"(요청|요구|건의|조치|개선|점검|정비|단속|시정|바랍니다|부탁드립니다|해주시)",
            flags=re.IGNORECASE,
        )
        self._observation_pattern = re.compile(r"(발생|지속|심각|문제|불편|위험|있어요|하고 있어요)")
        self._answer_like_pattern = re.compile(r"(귀하께서|아래와 같이 답변|처리 결과|회신|안내드립니다)")
        self._result_statuses = {"present", "pending", "insufficient"}
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

    def _build_result_field(
        self, text: str, start: int, end: int, confidence: float, status: str
    ) -> Dict[str, Any]:
        field = self._build_field(text, start, end, confidence)
        field["status"] = status if status in self._result_statuses else "pending"
        return field

    def _normalize_for_compare(self, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value or "")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _split_segments(self, text: str) -> Dict[str, Any]:
        """원문을 question/answer로 분리하고 입력 타입을 추정한다."""
        raw = text or ""
        q_marker = re.search(r"Q\s*[:：]", raw, flags=re.IGNORECASE)
        a_marker = re.search(r"A\s*[:：]", raw, flags=re.IGNORECASE)

        if q_marker and a_marker and q_marker.start() < a_marker.start():
            q_start = q_marker.end()
            a_start = a_marker.end()
            question = raw[q_start : a_marker.start()].strip()
            answer = raw[a_start:].strip()
            return {
                "question": question,
                "answer": answer,
                "question_offset": q_start,
                "answer_offset": a_start,
                "input_type": "TYPE_A",
            }

        answer_heading = re.search(r"(답변|회신|처리결과|조치결과|검토의견)\s*[:：]", raw)
        question_heading = re.search(r"(민원내용|문의내용|요청사항)\s*[:：]", raw)

        if answer_heading:
            q_start = question_heading.end() if question_heading else 0
            a_start = answer_heading.end()
            question = raw[q_start : answer_heading.start()].strip()
            answer = raw[a_start:].strip()
            input_type = "TYPE_A" if question and answer else "TYPE_C"
            return {
                "question": question or raw[: answer_heading.start()].strip(),
                "answer": answer,
                "question_offset": q_start,
                "answer_offset": a_start,
                "input_type": input_type,
            }

        input_type = "TYPE_B" if not self._answer_like_pattern.search(raw) else "TYPE_C"
        return {
            "question": raw.strip(),
            "answer": "",
            "question_offset": 0,
            "answer_offset": 0,
            "input_type": input_type,
        }

    def _sentence_candidates(self, text: str, base_offset: int = 0) -> List[Dict[str, Any]]:
        """문장 후보를 원문 인덱스와 함께 생성한다."""
        if not text:
            return []

        candidates: List[Dict[str, Any]] = []
        for m in re.finditer(r"[^\n.!?。]+[.!?。]?", text):
            start = m.start()
            end = m.end()
            raw_chunk = text[start:end]
            stripped = raw_chunk.strip()
            if len(stripped) < 5:
                continue

            leading = len(raw_chunk) - len(raw_chunk.lstrip())
            trailing = len(raw_chunk) - len(raw_chunk.rstrip())
            abs_start = base_offset + start + leading
            abs_end = base_offset + end - trailing
            candidates.append({"text": stripped, "start": abs_start, "end": abs_end})

        if not candidates and text.strip():
            stripped = text.strip()
            lead = len(text) - len(text.lstrip())
            trail = len(text) - len(text.rstrip())
            candidates.append(
                {
                    "text": stripped,
                    "start": base_offset + lead,
                    "end": base_offset + len(text) - trail,
                }
            )

        return candidates

    def _keyword_hits(self, text: str, keywords: List[str]) -> int:
        return sum(1 for k in keywords if k and k in text)

    def _score_candidate(
        self,
        sentence: Dict[str, Any],
        kind: str,
        idx: int,
        total: int,
        in_answer_segment: bool = False,
    ) -> float:
        text = sentence.get("text", "")
        length_score = min(len(text) / 80.0, 1.0)
        pos_ratio = (idx + 1) / max(total, 1)

        if kind == "observation":
            kw = self._keyword_hits(text, self._observation_keywords)
            pat = 1 if self._observation_pattern.search(text) else 0
            seg = 0.0 if in_answer_segment else 1.0
            pos = 1.0 - pos_ratio
            penalty = 0.25 if self._request_pattern.search(text) else 0.0
        elif kind == "request":
            kw = self._keyword_hits(text, self._request_keywords)
            pat = 1 if self._request_pattern.search(text) else 0
            seg = 0.0 if in_answer_segment else 1.0
            pos = pos_ratio
            penalty = 0.0
        elif kind == "context":
            kw = self._keyword_hits(text, self._context_keywords)
            pat = 1 if re.search(r"(년|월|일|시|최근|지난|매일|여름|겨울|봄|가을|신고|기존|이전)", text) else 0
            seg = 0.2 if in_answer_segment else 1.0
            pos = 1.0 - pos_ratio
            penalty = 0.0
        else:  # result
            kw = self._keyword_hits(text, self._result_keywords)
            pat = 1 if re.search(r"(답변|회신|처리|조치|완료|진행|예정|계획)", text) else 0
            seg = 1.0 if in_answer_segment else 0.0
            pos = pos_ratio
            penalty = 0.0

        return 0.35 * kw + 0.25 * pat + 0.20 * seg + 0.10 * length_score + 0.10 * pos - penalty

    def _score_to_confidence(self, score: float) -> float:
        if score >= 1.6:
            return 0.9
        if score >= 1.0:
            return 0.78
        if score >= 0.5:
            return 0.66
        return 0.55

    def _pick_best(self, candidates: List[Dict[str, Any]], kind: str, in_answer_segment: bool = False) -> Dict[str, Any]:
        if not candidates:
            return {"text": "", "start": 0, "end": 0, "score": 0.0}

        scored: List[Dict[str, Any]] = []
        total = len(candidates)
        for idx, sent in enumerate(candidates):
            score = self._score_candidate(sent, kind, idx, total, in_answer_segment=in_answer_segment)
            scored.append({**sent, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[0]

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
            segments = self._split_segments(text)
            question = segments["question"]
            answer = segments["answer"]

            q_candidates = self._sentence_candidates(question, base_offset=segments["question_offset"])
            a_candidates = self._sentence_candidates(answer, base_offset=segments["answer_offset"])

            best_obs = self._pick_best(q_candidates, "observation", in_answer_segment=False)
            best_req = self._pick_best(q_candidates, "request", in_answer_segment=False)
            best_ctx = self._pick_best(q_candidates, "context", in_answer_segment=False)

            obs_conf = self._score_to_confidence(best_obs.get("score", 0.0))
            req_conf = self._score_to_confidence(best_req.get("score", 0.0))
            ctx_conf = self._score_to_confidence(best_ctx.get("score", 0.0))

            if answer.strip():
                best_res = self._pick_best(a_candidates, "result", in_answer_segment=True)
                if best_res.get("score", 0.0) >= 0.5 and best_res.get("text"):
                    res_field = self._build_result_field(
                        best_res["text"],
                        best_res["start"],
                        best_res["end"],
                        self._score_to_confidence(best_res["score"]),
                        "present",
                    )
                else:
                    res_field = self._build_result_field("", 0, 0, 0.0, "insufficient")
            else:
                res_field = self._build_result_field("", 0, 0, 0.0, "pending")

            return {
                "observation": self._build_field(
                    best_obs.get("text", ""),
                    best_obs.get("start", 0),
                    best_obs.get("end", 0),
                    obs_conf,
                ),
                "result": res_field,
                "request": self._build_field(
                    best_req.get("text", ""),
                    best_req.get("start", 0),
                    best_req.get("end", 0),
                    req_conf,
                ),
                "context": self._build_field(
                    best_ctx.get("text", ""),
                    best_ctx.get("start", 0),
                    best_ctx.get("end", 0),
                    ctx_conf,
                ),
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

            for keyword in self._season_time_keywords:
                if keyword in text:
                    ent = ("TIME", keyword)
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
                else:
                    start, end = span
                    raw_text = str(data.get("raw_text") or "")
                    text_len = len(raw_text)
                    if field_name == "result" and field.get("status") == "pending":
                        if span != [0, 0]:
                            errors.append("invalid_pending_result_span")
                    else:
                        if not (0 <= start < end <= text_len):
                            errors.append(f"invalid_evidence_span_range:{field_name}")
                        else:
                            sliced = raw_text[start:end]
                            if self._normalize_for_compare(sliced) != self._normalize_for_compare(str(field.get("text") or "")):
                                errors.append(f"evidence_text_mismatch:{field_name}")

                if field_name == "result":
                    status = field.get("status")
                    if status is not None and status not in self._result_statuses:
                        errors.append("invalid_result_status")

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
            weights = {
                "observation": 0.30,
                "request": 0.30,
                "context": 0.25,
                "result": 0.15,
            }
            result_status = str(data.get("result", {}).get("status") or "")

            keys = ["observation", "request", "context", "result"]
            if result_status == "pending":
                keys = ["observation", "request", "context"]

            total_weight = sum(weights[k] for k in keys)
            if total_weight <= 0:
                return 0.0

            score = 0.0
            for key in keys:
                conf = float(data.get(key, {}).get("confidence") or 0.0)
                score += weights[key] * conf

            score = score / total_weight
            entity_bonus = min(len(data.get("entities", [])) * 0.01, 0.05)
            return max(0.0, min(1.0, score + entity_bonus))
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

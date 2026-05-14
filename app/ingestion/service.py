"""
데이터 입수 서비스

문서 로드, 정제, 중복 제거, PII 마스킹 등을 담당한다.

AI Hub 데이터 정규화 지원:
  - 국립아시아문화전당 (대화형: 고객/상담원)
  - 중앙행정기관      (Q/A형)
  - 지방행정기관      (제목+Q/A형)
"""

import re
import csv
import json
import hashlib
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional
from pathlib import Path
from app.core.logging import pipeline_logger
from app.core.exceptions import IngestionError

# ── AI Hub 기관 유형 상수 ──────────────────────────────────────────────────
_SOURCE_TYPE_CULTURAL = "cultural"   # 국립아시아문화전당 (고객/상담원 대화형)
_SOURCE_TYPE_CENTRAL = "central"     # 중앙행정기관 (Q/A형)
_SOURCE_TYPE_LOCAL = "local"         # 지방행정기관 (제목+Q/A형)

# 소스별 기본 카테고리 (consulting_category 필드 누락 파일 대비)
_SOURCE_DEFAULT_CATEGORY: Dict[str, str] = {
    "국립아시아문화전당": "문화관광",
}

# source 이름 → 상위 행정구역 매핑 (대한민국 전체 시·군·구 포함)
_REGION_MAP: Dict[str, str] = {
    # ── 특별시·광역시·특별자치시 ──────────────────────────────────────
    "서울": "서울", "서울시": "서울", "서울특별시": "서울",
    "부산": "부산", "부산시": "부산", "부산광역시": "부산",
    "대구": "대구", "대구시": "대구", "대구광역시": "대구",
    "인천": "인천", "인천시": "인천", "인천광역시": "인천",
    "광주": "광주", "광주시": "광주", "광주광역시": "광주",
    "대전": "대전", "대전시": "대전", "대전광역시": "대전",
    "울산": "울산", "울산시": "울산", "울산광역시": "울산",
    "세종": "세종", "세종시": "세종", "세종특별자치시": "세종",
    # ── 도 (광역) ──────────────────────────────────────────────────
    "경기": "경기도", "경기도": "경기도",
    "강원": "강원도", "강원도": "강원도", "강원특별자치도": "강원도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "전북": "전라북도", "전라북도": "전라북도", "전북특별자치도": "전라북도",
    "전남": "전라남도", "전라남도": "전라남도",
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "제주": "제주", "제주도": "제주", "제주특별자치도": "제주",
    # ── 서울시 자치구 ────────────────────────────────────────────────
    "강남구": "서울", "강동구": "서울", "강북구": "서울", "강서구": "서울",
    "관악구": "서울", "광진구": "서울", "구로구": "서울", "금천구": "서울",
    "노원구": "서울", "도봉구": "서울", "동대문구": "서울", "동작구": "서울",
    "마포구": "서울", "서대문구": "서울", "서초구": "서울", "성동구": "서울",
    "성북구": "서울", "송파구": "서울", "양천구": "서울", "영등포구": "서울",
    "용산구": "서울", "은평구": "서울", "종로구": "서울", "중구": "서울",
    "중랑구": "서울",
    # ── 부산시 자치구·군 ─────────────────────────────────────────────
    "금정구": "부산", "기장군": "부산", "동래구": "부산",
    "사상구": "부산", "사하구": "부산", "수영구": "부산",
    "연제구": "부산", "영도구": "부산", "해운대구": "부산",
    # 남구·동구·북구·서구는 여러 시에 존재 → 접두어 매칭으로 처리
    # ── 대구시 자치구·군 ─────────────────────────────────────────────
    "달서구": "대구", "달성군": "대구", "수성구": "대구",
    # ── 인천시 자치구·군 ─────────────────────────────────────────────
    "강화군": "인천", "계양구": "인천", "남동구": "인천",
    "미추홀구": "인천", "부평구": "인천", "연수구": "인천", "옹진군": "인천",
    # ── 광주시 자치구 ────────────────────────────────────────────────
    "광산구": "광주",
    # ── 대전시 자치구 ────────────────────────────────────────────────
    "대덕구": "대전", "유성구": "대전",
    # ── 울산시 자치구·군 ─────────────────────────────────────────────
    "울주군": "울산",
    # ── 경기도 시·군 (31개) ─────────────────────────────────────────
    "수원시": "경기도", "성남시": "경기도", "의정부시": "경기도",
    "안양시": "경기도", "부천시": "경기도", "광명시": "경기도",
    "평택시": "경기도", "동두천시": "경기도", "안산시": "경기도",
    "고양시": "경기도", "과천시": "경기도", "구리시": "경기도",
    "남양주시": "경기도", "오산시": "경기도", "시흥시": "경기도",
    "군포시": "경기도", "의왕시": "경기도", "하남시": "경기도",
    "용인시": "경기도", "파주시": "경기도", "이천시": "경기도",
    "안성시": "경기도", "김포시": "경기도", "화성시": "경기도",
    "양주시": "경기도", "포천시": "경기도", "여주시": "경기도",
    "연천군": "경기도", "가평군": "경기도", "양평군": "경기도",
    # 경기광주시: "광주시"는 광주광역시와 충돌 → 전용 키 사용
    "경기광주시": "경기도",
    # ── 강원도 시·군 (18개) ─────────────────────────────────────────
    "춘천시": "강원도", "원주시": "강원도", "강릉시": "강원도",
    "동해시": "강원도", "태백시": "강원도", "속초시": "강원도",
    "삼척시": "강원도", "홍천군": "강원도", "횡성군": "강원도",
    "영월군": "강원도", "평창군": "강원도", "정선군": "강원도",
    "철원군": "강원도", "화천군": "강원도", "양구군": "강원도",
    "인제군": "강원도", "양양군": "강원도",
    # 고성군: 강원/경남 중복 → 경남 우선 (하단 경남 항목 참조)
    # ── 충청북도 시·군 (11개) ───────────────────────────────────────
    "청주시": "충청북도", "충주시": "충청북도", "제천시": "충청북도",
    "보은군": "충청북도", "옥천군": "충청북도", "영동군": "충청북도",
    "증평군": "충청북도", "진천군": "충청북도", "괴산군": "충청북도",
    "음성군": "충청북도", "단양군": "충청북도",
    # ── 충청남도 시·군 (15개) ───────────────────────────────────────
    "천안시": "충청남도", "공주시": "충청남도", "보령시": "충청남도",
    "아산시": "충청남도", "서산시": "충청남도", "논산시": "충청남도",
    "계룡시": "충청남도", "당진시": "충청남도", "금산군": "충청남도",
    "부여군": "충청남도", "서천군": "충청남도", "청양군": "충청남도",
    "홍성군": "충청남도", "예산군": "충청남도", "태안군": "충청남도",
    # ── 전라북도 시·군 (14개) ───────────────────────────────────────
    "전주시": "전라북도", "군산시": "전라북도", "익산시": "전라북도",
    "정읍시": "전라북도", "남원시": "전라북도", "김제시": "전라북도",
    "완주군": "전라북도", "진안군": "전라북도", "무주군": "전라북도",
    "장수군": "전라북도", "임실군": "전라북도", "순창군": "전라북도",
    "고창군": "전라북도", "부안군": "전라북도",
    # ── 전라남도 시·군 (22개) ───────────────────────────────────────
    "목포시": "전라남도", "여수시": "전라남도", "순천시": "전라남도",
    "나주시": "전라남도", "광양시": "전라남도", "담양군": "전라남도",
    "곡성군": "전라남도", "구례군": "전라남도", "고흥군": "전라남도",
    "보성군": "전라남도", "화순군": "전라남도", "장흥군": "전라남도",
    "강진군": "전라남도", "해남군": "전라남도", "영암군": "전라남도",
    "무안군": "전라남도", "함평군": "전라남도", "영광군": "전라남도",
    "장성군": "전라남도", "완도군": "전라남도", "진도군": "전라남도",
    "신안군": "전라남도",
    # ── 경상북도 시·군 (23개) ───────────────────────────────────────
    "포항시": "경상북도", "경주시": "경상북도", "김천시": "경상북도",
    "안동시": "경상북도", "구미시": "경상북도", "영주시": "경상북도",
    "영천시": "경상북도", "상주시": "경상북도", "문경시": "경상북도",
    "경산시": "경상북도", "군위군": "경상북도", "의성군": "경상북도",
    "청송군": "경상북도", "영양군": "경상북도", "영덕군": "경상북도",
    "청도군": "경상북도", "고령군": "경상북도", "성주군": "경상북도",
    "칠곡군": "경상북도", "예천군": "경상북도", "봉화군": "경상북도",
    "울진군": "경상북도", "울릉군": "경상북도",
    # ── 경상남도 시·군 (18개) ───────────────────────────────────────
    "창원시": "경상남도", "진주시": "경상남도", "통영시": "경상남도",
    "사천시": "경상남도", "김해시": "경상남도", "밀양시": "경상남도",
    "거제시": "경상남도", "양산시": "경상남도", "의령군": "경상남도",
    "함안군": "경상남도", "창녕군": "경상남도", "고성군": "경상남도",
    "남해군": "경상남도", "하동군": "경상남도", "산청군": "경상남도",
    "함양군": "경상남도", "거창군": "경상남도", "합천군": "경상남도",
    # ── 제주특별자치도 시 ────────────────────────────────────────────
    "제주시": "제주", "서귀포시": "제주",
    # ── 문화기관 ─────────────────────────────────────────────────────
    "국립아시아문화전당": "광주",
}


class IngestionService:
    """데이터 입수 서비스"""

    def __init__(self):
        """초기화"""
        self.logger = pipeline_logger

    async def load_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """
        CSV 파일 로드

        Args:
            file_path: 파일 경로

        Returns:
            데이터 리스트
        """
        try:
            self.logger.info(f"CSV 파일 로드: {file_path}")
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                raise IngestionError(f"CSV 파일을 찾을 수 없습니다: {file_path}")

            rows: List[Dict[str, Any]] = []
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))

            self.logger.info(f"CSV 로드 완료: {len(rows)}건")
            return rows
        except Exception as e:
            self.logger.error(f"CSV 로드 실패: {str(e)}")
            raise IngestionError(f"CSV 로드 실패: {str(e)}") from e

    async def load_json(self, file_path: str) -> List[Dict[str, Any]]:
        """
        JSON 파일 로드

        Args:
            file_path: 파일 경로

        Returns:
            데이터 리스트
        """
        try:
            self.logger.info(f"JSON 파일 로드: {file_path}")
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                raise IngestionError(f"JSON 파일을 찾을 수 없습니다: {file_path}")

            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)

            if isinstance(payload, list):
                data = payload
            elif isinstance(payload, dict):
                if isinstance(payload.get("data"), list):
                    data = payload["data"]
                else:
                    data = [payload]
            else:
                raise IngestionError("JSON 루트는 object 또는 array여야 합니다.")

            records = [row for row in data if isinstance(row, dict)]
            self.logger.info(f"JSON 로드 완료: {len(records)}건")
            return records
        except Exception as e:
            self.logger.error(f"JSON 로드 실패: {str(e)}")
            raise IngestionError(f"JSON 로드 실패: {str(e)}") from e

    async def clean_text(self, text: str) -> str:
        """
        텍스트 정제

        Args:
            text: 원본 텍스트

        Returns:
            정제된 텍스트
        """
        try:
            self.logger.debug(f"텍스트 정제: {text[:50]}...")
            if text is None:
                return ""

            cleaned = str(text)
            cleaned = cleaned.replace("_x000D_", " ")
            cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
            cleaned = cleaned.replace("\t", " ")

            cleaned = "".join(ch for ch in cleaned if ch == "\n" or ord(ch) >= 32)
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
            cleaned = re.sub(r"[ \u00A0]{2,}", " ", cleaned)
            cleaned = re.sub(r" ?\n ?", "\n", cleaned)
            cleaned = cleaned.strip()

            return cleaned
        except Exception as e:
            self.logger.error(f"텍스트 정제 실패: {str(e)}")
            raise IngestionError(f"텍스트 정제 실패: {str(e)}") from e

    async def mask_pii(self, text: str) -> str:
        """
        개인정보 마스킹

        Args:
            text: 원본 텍스트

        Returns:
            마스킹된 텍스트
        """
        try:
            self.logger.debug(f"PII 마스킹: {text[:50]}...")
            if text is None:
                return ""

            masked = str(text)

            pii_patterns = [
                (r"\b01[0-9][-.]?\d{3,4}[-.]?\d{4}\b", "PHONE"),
                (r"\b\d{2,3}[-.]?\d{3,4}[-.]?\d{4}\b", "PHONE"),
                (r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)", "SSN"),
                (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "EMAIL"),
                (r"\b(?:\d{2,6}-){2,}\d{2,6}\b", "ACCOUNT"),
                (r"\b\d{2,3}[가-힣]\d{4}\b", "VEHICLE"),
            ]

            for pattern, label in pii_patterns:
                masked = re.sub(pattern, f"[REDACTED:{label}]", masked)

            return masked
        except Exception as e:
            self.logger.error(f"PII 마스킹 실패: {str(e)}")
            raise IngestionError(f"PII 마스킹 실패: {str(e)}") from e

    def _document_signature(self, text: str) -> str:
        normalized = self._normalize_for_dedup(text)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _normalize_for_dedup(self, text: str) -> str:
        base = " ".join((text or "").lower().split())
        return re.sub(r"[^a-z0-9가-힣\s]+", "", base)

    def _is_near_duplicate(self, text_a: str, text_b: str, threshold: float = 0.96) -> bool:
        normalized_a = self._normalize_for_dedup(text_a)
        normalized_b = self._normalize_for_dedup(text_b)
        if not normalized_a or not normalized_b:
            return False
        return SequenceMatcher(None, normalized_a, normalized_b).ratio() >= threshold

    async def deduplicate(
        self, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        중복 제거

        Args:
            documents: 문서 리스트

        Returns:
            중복이 제거된 문서 리스트
        """
        # try:
        #     total = len(documents)
        #     self.logger.info(f"중복 제거 시작: {total}개 문서")
        #     unique_docs: List[Dict[str, Any]] = []
        #     seen_signatures = set()
        #     near_duplicate_texts: List[str] = []
        #     last_logged_pct = -1
        #
        #     for i, doc in enumerate(documents):
        #         text = str(doc.get("text") or "").strip()
        #         signature = self._document_signature(text)
        #         if signature in seen_signatures:
        #             continue
        #
        #         if any(self._is_near_duplicate(text, seen_text) for seen_text in near_duplicate_texts):
        #             continue
        #
        #         seen_signatures.add(signature)
        #         near_duplicate_texts.append(text)
        #         unique_docs.append(doc)
        #
        #         pct = int((i + 1) / total * 100) if total else 100
        #         if pct % 10 == 0 and pct != last_logged_pct:
        #             self.logger.info(f"중복 제거 진행: {pct}% ({i + 1}/{total}), 고유 문서: {len(unique_docs)}개")
        #             last_logged_pct = pct
        #
        #     self.logger.info(f"중복 제거 완료: {total} -> {len(unique_docs)}")
        #     return unique_docs
        # except Exception as e:
        #     self.logger.error(f"중복 제거 실패: {str(e)}")
        #     raise IngestionError(f"중복 제거 실패: {str(e)}") from e
        return documents

    # ──────────────────────────────────────────────────────────────────
    # AI Hub 원천데이터 정규화
    # ──────────────────────────────────────────────────────────────────

    def _parse_consulting_date(self, date_str: str) -> str:
        """YYYYMMDD → ISO 8601 KST (+09:00)."""
        kst = timezone(timedelta(hours=9))
        value = (date_str or "").strip()
        if not value:
            return datetime.now(kst).isoformat()
        try:
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=kst).isoformat()
        except ValueError:
            return datetime.now(kst).isoformat()

    def _detect_source_type(self, record: Dict[str, Any]) -> str:
        """consulting_content 형식과 source 이름으로 기관 유형을 감지한다.

        감지 우선순위:
          1. source = "국립아시아문화전당"                → cultural
          2. source 이름이 부(ministry)/처(administration) → central 우선 확정
             청(agency): 시청/도청/군청/구청 제외 시 central
          3. consulting_content 첫 줄이 "고객:" / "상담원:" → cultural
          4. source 이름이 행정 지역명 (REGION_MAP 또는 도·시·군·구 접미사) → local
          5. consulting_content 첫 줄이 "제목 :"           → local
          6. 나머지                                        → central (기본값)
        """
        source = str(record.get("source") or "")
        content = str(record.get("consulting_content") or "").strip()

        # 1. 국립아시아문화전당 최우선
        if "국립아시아문화전당" in source:
            return _SOURCE_TYPE_CULTURAL

        # 2. 중앙행정기관 source 이름 우선 감지
        #    부(ministry)/처(administration): 항상 중앙
        #    청(agency): 시청/도청/군청/구청은 지방이므로 제외
        if any(source.endswith(s) for s in ("부", "처")):
            return _SOURCE_TYPE_CENTRAL
        if source.endswith("청") and not re.search(r"[시도군구]청$", source):
            return _SOURCE_TYPE_CENTRAL

        # 3. 대화형 content
        if re.search(r"^(?:고객|상담원)\s*[:：]", content):
            return _SOURCE_TYPE_CULTURAL

        # 4. 행정 지역명 → local
        if source in _REGION_MAP and source != "국립아시아문화전당":
            return _SOURCE_TYPE_LOCAL
        if any(source.endswith(s) for s in ("도", "시", "군", "구")):
            return _SOURCE_TYPE_LOCAL

        # 5. 제목+Q/A형 content → local (source 감지 실패 시 content로 fallback)
        if re.search(r"^제목\s*[:：]", content):
            return _SOURCE_TYPE_LOCAL

        return _SOURCE_TYPE_CENTRAL

    def _extract_region(self, source: str, source_type: str) -> str:
        """source 이름에서 행정 지역명을 반환한다."""
        if source_type == _SOURCE_TYPE_CENTRAL:
            return "전국"
        if source in _REGION_MAP:
            return _REGION_MAP[source]
        # 접두어 매칭 (예: "서울 중구" → "서울")
        for key, region in _REGION_MAP.items():
            if len(key) >= 2 and source.startswith(key):
                return region
        return "unknown"

    def _clean_aihub_markup(self, text: str) -> str:
        """AI Hub 비식별화 기호 및 인코딩 잔재를 정규화한다.

        _x000D_ → 공백 (엑셀/HTML 캐리지리턴 인코딩 잔재)
        ▲▲▲  (2개 이상) → [REDACTED:NAME]   (담당자 이름)
        ○○○○ (2개 이상) → [REDACTED:ENTITY] (기관·인명·주소)
        """
        text = text.replace("_x000D_", " ")
        text = re.sub(r"▲{2,}", "[REDACTED:NAME]", text)
        text = re.sub(r"○{2,}", "[REDACTED:ENTITY]", text)
        return text

    def normalize_aihub_record(
        self,
        record: Dict[str, Any],
        source_file: str = "",
    ) -> Dict[str, Any]:
        """AI Hub 원천데이터 레코드를 내부 스키마로 정규화한다.

        국립아시아문화전당 / 중앙행정기관 / 지방행정기관 세 유형을
        자동 감지하여 통일된 필드 구조로 변환한다.

        Returns::
            {
              case_id, source, source_id, created_at,
              category, region, raw_text, text,
              metadata: {source_type, source_file, consulting_date,
                         client_gender, client_age,
                         consulting_turns, consulting_length},
              instructions,
            }
        """
        source = str(record.get("source") or "").strip()
        source_id = str(record.get("source_id") or "").strip()
        source_type = self._detect_source_type(record)

        case_id = f"{source}_{source_id}" if source_id else f"AUTO-{source}"
        created_at = self._parse_consulting_date(
            str(record.get("consulting_date") or "").strip()
        )
        category = str(record.get("consulting_category") or "").strip()
        if not category:
            category = _SOURCE_DEFAULT_CATEGORY.get(source, "unknown")
        region = self._extract_region(source, source_type)

        content = self._clean_aihub_markup(
            str(record.get("consulting_content") or "").strip()
        )

        def _to_int(v: Any) -> Optional[int]:
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        return {
            "case_id": case_id,
            "source": source,
            "source_id": source_id,
            "created_at": created_at,
            "category": category,
            "region": region,
            "raw_text": content,
            "text": content,
            "metadata": {
                "source_type": source_type,
                "source_file": str(source_file),
                "consulting_date": str(record.get("consulting_date") or "").strip(),
                "client_gender": str(record.get("client_gender") or "").strip(),
                "client_age": str(record.get("client_age") or "").strip(),
                "consulting_turns": _to_int(record.get("consulting_turns")),
                "consulting_length": _to_int(record.get("consulting_length")),
            },
            "instructions": (
                record.get("instructions")
                if isinstance(record.get("instructions"), list)
                else []
            ),
        }

    async def load_and_normalize(self, file_path: str) -> List[Dict[str, Any]]:
        """단일 JSON 파일을 로드하고 정규화한다."""
        try:
            records = await self.load_json(file_path)
            return [
                self.normalize_aihub_record(r, source_file=file_path) for r in records
            ]
        except Exception as exc:
            self.logger.error(f"load_and_normalize 실패: {file_path} — {exc}")
            raise IngestionError(f"load_and_normalize 실패: {exc}") from exc

    async def load_training_directory(
        self,
        base_dir: str,
        source_subdir: str = "01.원천데이터",
        label_subdir: str = "02.라벨링데이터",
        include_labels: bool = True,
    ) -> List[Dict[str, Any]]:
        """Training 디렉토리 전체를 로드하고 정규화한다.

        원천데이터를 기준으로 레코드를 구성하고,
        라벨링데이터(분류/요약/질의응답)를 source_id 기준으로 병합한다.

        Args:
            base_dir:       Training 루트 경로
            source_subdir:  원천데이터 하위 디렉토리 이름
            label_subdir:   라벨링데이터 하위 디렉토리 이름
            include_labels: 라벨링 데이터 병합 여부

        Returns:
            정규화된 레코드 리스트
        """
        try:
            base_path = Path(base_dir)
            source_path = base_path / source_subdir

            if not source_path.exists():
                raise IngestionError(
                    f"원천데이터 디렉토리가 없습니다: {source_path}"
                )

            self.logger.info(f"Training 디렉토리 로드 시작: {base_dir}")

            # ── 1단계: 원천데이터 로드 ──────────────────────────────
            source_map: Dict[str, Dict[str, Any]] = {}
            source_files = sorted(source_path.rglob("*.json"))
            self.logger.info(f"원천데이터 파일 수: {len(source_files)}")

            for json_file in source_files:
                try:
                    for rec in await self.load_json(str(json_file)):
                        normalized = self.normalize_aihub_record(
                            rec, source_file=str(json_file)
                        )
                        key = f"{normalized['source']}_{normalized['source_id']}"
                        source_map[key] = normalized
                except Exception as exc:
                    self.logger.warning(
                        f"원천데이터 로드 실패 (건너뜀): {json_file} — {exc}"
                    )

            self.logger.info(f"원천데이터 정규화 완료: {len(source_map)}건")

            if not include_labels:
                return list(source_map.values())

            # ── 2단계: 라벨링 데이터 병합 ───────────────────────────
            label_path = base_path / label_subdir
            if not label_path.exists():
                self.logger.warning(
                    f"라벨링 디렉토리 없음, 원천데이터만 반환: {label_path}"
                )
                return list(source_map.values())

            label_files = sorted(label_path.rglob("*.json"))
            self.logger.info(f"라벨링 파일 수: {len(label_files)}")

            # key → instructions 누적 (분류/요약/질의응답 통합)
            label_map: Dict[str, List[Dict[str, Any]]] = {}
            for json_file in label_files:
                try:
                    for rec in await self.load_json(str(json_file)):
                        source = str(rec.get("source") or "").strip()
                        source_id = str(rec.get("source_id") or "").strip()
                        key = f"{source}_{source_id}"
                        instructions = rec.get("instructions")
                        if isinstance(instructions, list):
                            label_map.setdefault(key, []).extend(instructions)
                except Exception as exc:
                    self.logger.warning(
                        f"라벨링 데이터 로드 실패 (건너뜀): {json_file} — {exc}"
                    )

            # instructions 병합
            matched = sum(
                1
                for key, instr in label_map.items()
                if key in source_map
                and source_map[key].__setitem__("instructions", instr) is None
            )
            self.logger.info(
                f"라벨링 병합 완료: {matched}/{len(source_map)}건 매칭"
            )
            return list(source_map.values())

        except IngestionError:
            raise
        except Exception as exc:
            self.logger.error(f"Training 디렉토리 로드 실패: {exc}")
            raise IngestionError(f"Training 디렉토리 로드 실패: {exc}") from exc

    async def process(
        self, documents: List[Dict[str, Any]], clean: bool = True, mask_pii: bool = True
    ) -> List[Dict[str, Any]]:
        """
        종합 처리 파이프라인

        Args:
            documents: 원본 문서 리스트
            clean: 정제 여부
            mask_pii: PII 마스킹 여부

        Returns:
            처리된 문서 리스트
        """
        try:
            self.logger.info(f"입수 처리 시작: {len(documents)}개 문서")
            result = documents

            if clean:
                result = [
                    {**doc, "text": await self.clean_text(doc.get("text", ""))}
                    for doc in result
                ]
                self.logger.info("텍스트 정제 완료")

            if mask_pii:
                result = [
                    {**doc, "text": await self.mask_pii(doc.get("text", ""))}
                    for doc in result
                ]
                self.logger.info("PII 마스킹 완료")

            # result = await self.deduplicate(result)
            self.logger.info(f"입수 처리 완료: {len(result)}개 문서")

            return result
        except Exception as e:
            self.logger.error(f"입수 처리 실패: {str(e)}")
            raise IngestionError(f"입수 처리 실패: {str(e)}") from e


# 싱글톤
_ingestion_service = None


def get_ingestion_service() -> IngestionService:
    """입수 서비스 인스턴스 반환"""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService()
    return _ingestion_service

"""
데이터 입수 서비스

문서 로드, 정제, 중복 제거, PII 마스킹 등을 담당한다.
"""

import re
import csv
import json
import hashlib
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional
from pathlib import Path
from app.core.logging import pipeline_logger
from app.core.exceptions import IngestionError


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
        try:
            self.logger.info(f"중복 제거 시작: {len(documents)}개 문서")
            unique_docs: List[Dict[str, Any]] = []
            seen_signatures = set()
            near_duplicate_texts: List[str] = []

            for doc in documents:
                text = str(doc.get("text") or "").strip()
                signature = self._document_signature(text)
                if signature in seen_signatures:
                    continue

                if any(self._is_near_duplicate(text, seen_text) for seen_text in near_duplicate_texts):
                    continue

                seen_signatures.add(signature)
                near_duplicate_texts.append(text)
                unique_docs.append(doc)

            self.logger.info(f"중복 제거 완료: {len(documents)} -> {len(unique_docs)}")
            return unique_docs
        except Exception as e:
            self.logger.error(f"중복 제거 실패: {str(e)}")
            raise IngestionError(f"중복 제거 실패: {str(e)}") from e

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

            result = await self.deduplicate(result)
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

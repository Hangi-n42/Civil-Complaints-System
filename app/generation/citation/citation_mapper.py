"""Citation 매핑 및 정합성 검증"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.exceptions import GenerationError
from app.core.logging import pipeline_logger


class CitationMapper:
    """Citation 정합성 검증 담당"""

    SNIPPET_MAX_CHARS = 200

    def __init__(self):
        self.logger = pipeline_logger

    def validate_citations_against_context(
        self,
        citations: List[Dict[str, Any]],
        retrieval_context: List[Dict[str, Any]],
    ) -> Tuple[bool, int, List[str]]:
        """
        생성된 citation이 retrieval_context와 일치하는지 검증한다.

        Args:
            citations: 생성된 citation 리스트
            retrieval_context: 검색 컨텍스트

        Returns:
            (is_valid, mismatch_count, mismatch_details)
        """
        # retrieval_context에서 chunk_id/case_id 매핑 구성
        valid_citations: Set[Tuple[str, str]] = set()
        context_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for item in retrieval_context:
            chunk_id = str(item.get("chunk_id", "")).strip()
            case_id = str(item.get("case_id", "")).strip()
            snippet = str(item.get("snippet", "")).strip()

            if chunk_id and case_id:
                key = (chunk_id, case_id)
                valid_citations.add(key)
                context_map[key] = {"snippet": snippet}

        # citation 검증
        mismatches: List[str] = []

        for idx, citation in enumerate(citations):
            chunk_id = str(citation.get("chunk_id", "")).strip()
            case_id = str(citation.get("case_id", "")).strip()
            snippet = str(citation.get("snippet", "")).strip()

            # 1. chunk_id/case_id 일치 확인
            key = (chunk_id, case_id)
            if key not in valid_citations:
                mismatches.append(
                    f"Citation #{idx}: chunk_id={chunk_id}, case_id={case_id} not in retrieval_context"
                )
                continue

            # 2. snippet 길이 검증
            if len(snippet) > self.SNIPPET_MAX_CHARS:
                mismatches.append(
                    f"Citation #{idx}: snippet exceeds max_chars ({len(snippet)} > {self.SNIPPET_MAX_CHARS})"
                )

            # 3. 선택적: snippet 유사성 검증 (원문과 일치하는지)
            original_snippet = context_map[key]["snippet"]
            if original_snippet and snippet not in original_snippet:
                self.logger.warning(
                    "citation_snippet_mismatch citation_chunk_id=%s snippet_match=false",
                    chunk_id,
                )

        is_valid = len(mismatches) == 0
        mismatch_count = len(mismatches)

        return is_valid, mismatch_count, mismatches

    def extract_chunk_and_case_ids(self, retrieval_context: List[Dict[str, Any]]) -> Set[str]:
        """
        retrieval_context에서 chunk_id와 case_id 조합을 추출한다.
        """
        ids = set()
        for item in retrieval_context:
            chunk_id = str(item.get("chunk_id", "")).strip()
            case_id = str(item.get("case_id", "")).strip()
            if chunk_id and case_id:
                ids.add(f"{chunk_id}:{case_id}")
        return ids


def get_citation_mapper() -> CitationMapper:
    """Citation mapper 싱글톤"""
    if not hasattr(get_citation_mapper, "_instance"):
        get_citation_mapper._instance = CitationMapper()
    return get_citation_mapper._instance

"""
검색 서비스 (Retrieval)

Week 1 기준선 구현:
- 샘플/구조화 레코드 정규화
- 인메모리 인덱싱
- 메타데이터 필터 검색
- FE/QA 연동용 응답 포맷 생성
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.core.logging import pipeline_logger
from app.core.exceptions import RetrievalError
from app.core.config import settings
from app.core.title_builder import build_case_title
from app.retrieval.entity_labels import ALLOWED_ENTITY_LABELS
from app.retrieval.vectorstores.chroma_store import ChromaVectorStore


class RetrievalService:
    """검색 서비스"""

    def __init__(self):
        """초기화"""
        self.logger = pipeline_logger
        self.embedding_model = settings.EMBEDDING_MODEL
        self.vectorstore_path = settings.CHROMA_DB_PATH
        self.embedding_device = settings.EMBEDDING_DEVICE
        self.default_collection_name = "civil_cases_v1"
        self._vectorstore: Optional[ChromaVectorStore] = None

    def _get_vectorstore(self) -> ChromaVectorStore:
        if self._vectorstore is None:
            self._vectorstore = ChromaVectorStore(
                persist_directory=self.vectorstore_path,
                embedding_model_name=self.embedding_model,
                embedding_device=self.embedding_device,
            )
        return self._vectorstore

    def _bootstrap_from_samples(self, collection_name: Optional[str] = None) -> None:
        """샘플 데이터가 존재하면 ChromaDB 컬렉션을 초기화한다."""
        collection_key = collection_name or self.default_collection_name
        sample_path = Path(settings.SAMPLES_DATA_PATH) / "sample_cases.json"
        if not sample_path.exists():
            self.logger.info("샘플 데이터 없음: 초기 인덱스 비어 있음")
            return

        try:
            with sample_path.open("r", encoding="utf-8") as f:
                sample_records = json.load(f)
            if isinstance(sample_records, list) and sample_records:
                store = self._get_vectorstore()
                if store.count(collection_key) == 0:
                    normalized = [
                        self._normalize_record(record, index=index)
                        for index, record in enumerate(sample_records)
                        if isinstance(record, dict)
                    ]
                    store.upsert_records(collection_key, normalized)
                self.logger.info(f"샘플 인덱스 로드 완료: {len(sample_records)}개 레코드")
        except Exception as e:
            self.logger.warning(f"샘플 인덱스 로드 실패: {str(e)}")

    def _normalize_case_id(self, record: Dict[str, Any], index: int) -> str:
        raw_case_id = record.get("case_id") or record.get("id")
        if not raw_case_id:
            return f"CASE-UNKNOWN-{index:06d}"

        case_id = str(raw_case_id).strip().upper()
        normalized = re.sub(r"[^A-Z0-9]+", "-", case_id).strip("-")

        if normalized.startswith("CASE-"):
            return normalized
        return f"CASE-{normalized}"

    def _normalize_created_at(self, record: Dict[str, Any]) -> str:
        raw_created_at = (
            record.get("created_at")
            or record.get("submitted_at")
            or record.get("date")
            or record.get("datetime")
        )
        kst = timezone(timedelta(hours=9))

        if not raw_created_at:
            return datetime.now(kst).isoformat()

        try:
            parsed = datetime.fromisoformat(str(raw_created_at).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=kst)
            return parsed.isoformat()
        except ValueError:
            # yyyy-mm-dd 형식 대응
            try:
                parsed = datetime.strptime(str(raw_created_at), "%Y-%m-%d")
                return parsed.replace(tzinfo=kst).isoformat()
            except ValueError:
                return datetime.now(kst).isoformat()

    def _extract_entities(
        self, record: Dict[str, Any]
    ) -> tuple[List[str], List[str], float]:
        entities = record.get("entities")
        entity_pairs: List[tuple[str, str]] = []
        confidence_values: List[float] = []

        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                label = str(entity.get("label", "")).strip().upper()
                text = str(entity.get("text", "")).strip()
                if label in ALLOWED_ENTITY_LABELS and text:
                    entity_pairs.append((label, text))
                confidence = entity.get("confidence")
                if isinstance(confidence, (int, float)):
                    confidence_values.append(float(confidence))

        for field in ("observation", "result", "request", "context"):
            value = record.get(field)
            if isinstance(value, dict):
                field_confidence = value.get("confidence")
                if isinstance(field_confidence, (int, float)):
                    confidence_values.append(float(field_confidence))

        metadata = record.get("metadata")
        if isinstance(metadata, dict):
            metadata_confidence = metadata.get("confidence")
            if isinstance(metadata_confidence, (int, float)):
                confidence_values.append(float(metadata_confidence))

        unique_pairs: List[tuple[str, str]] = []
        seen_pairs = set()
        for pair in entity_pairs:
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            unique_pairs.append(pair)

        unique_labels = [label for label, _ in unique_pairs]
        unique_texts = [text for _, text in unique_pairs]
        confidence_avg = (
            round(sum(confidence_values) / len(confidence_values), 4)
            if confidence_values
            else 0.0
        )

        if not unique_labels:
            raw_labels = record.get("entity_labels")
            raw_texts = record.get("entity_texts")
            if isinstance(raw_labels, list):
                fallback_pairs: List[tuple[str, str]] = []
                seen_fallback = set()
                for idx, label in enumerate(raw_labels):
                    normalized_label = str(label).strip().upper()
                    if normalized_label not in ALLOWED_ENTITY_LABELS or normalized_label in seen_fallback:
                        continue
                    seen_fallback.add(normalized_label)
                    fallback_text = ""
                    if isinstance(raw_texts, list) and idx < len(raw_texts):
                        fallback_text = str(raw_texts[idx]).strip()
                    fallback_pairs.append((normalized_label, fallback_text))

                if fallback_pairs:
                    unique_labels = [label for label, _ in fallback_pairs]
                    unique_texts = [text for _, text in fallback_pairs]

        return unique_labels, unique_texts, confidence_avg

    def _normalize_chunk_id(self, case_id: str, record: Dict[str, Any], index: int) -> str:
        candidate = str(record.get("chunk_id") or "").strip()
        if candidate and re.fullmatch(rf"{re.escape(case_id)}__chunk-\d+", candidate):
            return candidate

        raw_index = record.get("chunk_index", index)
        try:
            chunk_index = max(0, int(raw_index))
        except (TypeError, ValueError):
            chunk_index = max(0, index)

        return f"{case_id}__chunk-{chunk_index}"

    def _get_observation_text(self, record: Dict[str, Any]) -> str:
        observation = record.get("observation")
        if isinstance(observation, dict):
            return str(observation.get("text", "")).strip()

        summary = record.get("summary")
        if isinstance(summary, dict):
            return str(summary.get("observation", "")).strip()

        structured_text = record.get("structured_text")
        if isinstance(structured_text, dict):
            return str(structured_text.get("observation", "")).strip()

        return ""

    def _get_request_text(self, record: Dict[str, Any]) -> str:
        request = record.get("request")
        if isinstance(request, dict):
            return str(request.get("text", "")).strip()

        summary = record.get("summary")
        if isinstance(summary, dict):
            return str(summary.get("request", "")).strip()

        structured_text = record.get("structured_text")
        if isinstance(structured_text, dict):
            return str(structured_text.get("request", "")).strip()

        return ""

    def _build_chunk_text(self, record: Dict[str, Any]) -> str:
        structured_text = record.get("structured_text")
        if isinstance(structured_text, dict):
            ordered = [
                str(structured_text.get("observation", "")).strip(),
                str(structured_text.get("result", "")).strip(),
                str(structured_text.get("request", "")).strip(),
                str(structured_text.get("context", "")).strip(),
            ]
            text = "\n".join(item for item in ordered if item)
            if text:
                return text

        sections: List[str] = []
        for field in ("observation", "result", "request", "context"):
            value = record.get(field)
            if isinstance(value, dict):
                text = str(value.get("text", "")).strip()
                if text:
                    sections.append(text)

        if sections:
            return "\n".join(sections)

        raw_text = str(record.get("raw_text", "")).strip()
        if raw_text:
            return raw_text

        return str(record.get("text", "")).strip()

    def _normalize_record(self, record: Dict[str, Any], index: int) -> Dict[str, Any]:
        case_id = self._normalize_case_id(record, index=index)
        doc_id = str(record.get("doc_id") or case_id)
        created_at = self._normalize_created_at(record)
        created_at_ts = int(datetime.fromisoformat(created_at).timestamp())

        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        source = (
            str(record.get("source") or metadata.get("source") or "unknown").strip()
            or "unknown"
        )

        category = record.get("category")
        region = record.get("region")
        if region is None:
            region = metadata.get("region")

        entity_labels, entity_texts, confidence = self._extract_entities(record)

        chunk_text = self._build_chunk_text(record)
        chunk_id = self._normalize_chunk_id(case_id=case_id, record=record, index=index)
        try:
            chunk_index = int(str(chunk_id).rsplit("-", 1)[-1])
        except (TypeError, ValueError):
            chunk_index = index

        title = build_case_title(
            observation=self._get_observation_text(record),
            request=self._get_request_text(record),
            chunk_text=chunk_text,
            category=category,
        )

        return {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "case_id": case_id,
            "chunk_text": chunk_text,
            "chunk_type": str(record.get("chunk_type", "combined")),
            "source": source,
            "created_at": created_at,
            "created_at_ts": created_at_ts,
            "chunk_index": chunk_index,
            "category": category,
            "region": region,
            "title": title,
            "entity_labels": entity_labels,
            "entity_texts": entity_texts,
            "summary": {
                "observation": self._get_observation_text(record),
                "request": self._get_request_text(record),
            },
            "metadata": {
                "pipeline_version": "week2",
                "structuring_confidence": confidence,
                "content_type": "full",
                "created_at_ts": created_at_ts,
            },
        }

    def _index_documents_internal(
        self,
        documents: List[Dict[str, Any]],
        rebuild: bool = False,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_documents = [
            self._normalize_record(record, index=index)
            for index, record in enumerate(documents)
            if isinstance(record, dict)
        ]

        store = self._get_vectorstore()
        collection_key = collection_name or self.default_collection_name
        if rebuild:
            store.reset_collection(collection_key)

        result = store.upsert_records(collection_key, normalized_documents)
        return {
            "indexed_count": int(result.get("indexed_count", 0)),
            "chunk_count": int(result.get("chunk_count", 0)),
            "index_name": collection_key,
            "rebuild": rebuild,
            "records": result.get("records", []),
        }

    def _tokenize(self, text: str) -> set[str]:
        tokens = re.findall(r"[A-Za-z0-9가-힣_]+", text.lower())
        return {token for token in tokens if token.strip()}

    def _score(self, query: str, chunk_text: str) -> float:
        query_tokens = self._tokenize(query)
        doc_tokens = self._tokenize(chunk_text)

        if not query_tokens or not doc_tokens:
            return 0.0

        intersection = len(query_tokens.intersection(doc_tokens))
        union = len(query_tokens.union(doc_tokens))
        jaccard = intersection / union if union else 0.0

        text_lower = chunk_text.lower()
        bonus = 0.0
        for token in query_tokens:
            if len(token) >= 2 and token in text_lower:
                bonus = 0.15
                break

        return round(min(1.0, jaccard + bonus), 4)

    def _within_range(
        self, created_at: str, date_from: Optional[str], date_to: Optional[str]
    ) -> bool:
        try:
            current = datetime.fromisoformat(created_at)
        except ValueError:
            return True

        if date_from:
            try:
                start = datetime.fromisoformat(date_from)
                if current < start:
                    return False
            except ValueError:
                pass

        if date_to:
            try:
                end = datetime.fromisoformat(date_to)
                if current > end:
                    return False
            except ValueError:
                pass

        return True

    def _matches_filters(self, chunk: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        if not filters:
            return True

        region = filters.get("region")
        if region:
            chunk_region = str(chunk.get("region") or "")
            if region not in chunk_region:
                return False

        category = filters.get("category")
        if category:
            if str(chunk.get("category") or "") != str(category):
                return False

        created_at = filters.get("created_at")
        if created_at:
            if str(chunk.get("created_at") or "") != str(created_at):
                return False

        if not self._within_range(
            chunk.get("created_at", ""),
            filters.get("date_from"),
            filters.get("date_to"),
        ):
            return False

        label_filters = filters.get("entity_labels")
        if isinstance(label_filters, list) and label_filters:
            current_labels = {
                str(label).upper()
                for label in chunk.get("entity_labels", [])
                if str(label).upper() in ALLOWED_ENTITY_LABELS
            }
            if not current_labels.intersection({str(item).upper() for item in label_filters}):
                return False

        return True

    def _build_snippet(self, chunk_text: str, max_length: int = 120) -> str:
        text = " ".join(chunk_text.split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."

    def _build_title(self, chunk: Dict[str, Any], max_length: int = 60) -> str:
        summary = chunk.get("summary") or {}
        return build_case_title(
            observation=summary.get("observation"),
            request=summary.get("request"),
            chunk_text=chunk.get("chunk_text"),
            category=chunk.get("category"),
            max_length=max_length,
        )

    def _normalize_request_segments(
        self,
        query: str,
        request_segments: Optional[List[str]] = None,
    ) -> List[str]:
        raw_segments = request_segments or []
        cleaned_segments = [
            " ".join(str(segment or "").split())
            for segment in raw_segments
            if str(segment or "").strip()
        ]
        if cleaned_segments:
            return cleaned_segments

        segments = [str(query or "").strip()]
        for delimiter in (" 및 ", " 그리고 ", ",", ";"):
            next_segments: List[str] = []
            for segment in segments:
                next_segments.extend(segment.split(delimiter))
            segments = next_segments

        normalized = [" ".join(segment.split()) for segment in segments if segment.strip()]
        if len(normalized) <= 1:
            return []
        return normalized

    def _apply_retrieval_policy(
        self,
        results: List[Dict[str, Any]],
        *,
        topic_type: Optional[str],
        retrieval_policy: Optional[str],
    ) -> List[Dict[str, Any]]:
        policy = str(retrieval_policy or "general").strip() or "general"
        if policy == "general":
            for item in results:
                metadata = item.setdefault("metadata", {})
                metadata["retrieval_policy"] = policy
                if topic_type:
                    metadata["topic_type"] = topic_type
            return results

        policy_keywords = {
            "admin_policy": ("법", "법령", "조례", "규정", "기준", "절차", "급여", "복지", "수급", "임대주택"),
            "field_ops": ("현장", "점검", "보수", "공사", "도로", "시설", "소음", "악취", "가로등", "안전"),
        }.get(policy, ())

        boosted: List[Dict[str, Any]] = []
        for item in results:
            metadata = item.setdefault("metadata", {})
            summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
            searchable = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                    str(metadata.get("category") or ""),
                    str(summary.get("observation") or ""),
                    str(summary.get("request") or ""),
                ]
            )
            has_policy_match = any(keyword in searchable for keyword in policy_keywords)
            boost = 0.04 if has_policy_match else 0.0
            item["score"] = round(min(1.0, float(item.get("score", 0.0) or 0.0) + boost), 4)
            metadata["retrieval_policy"] = policy
            metadata["policy_boost"] = boost
            if topic_type:
                metadata["topic_type"] = topic_type
            boosted.append(item)

        boosted.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
        for rank, item in enumerate(boosted, start=1):
            item["rank"] = rank
        return boosted

    def _merge_segment_results(
        self,
        segment_results: List[tuple[str, List[Dict[str, Any]]]],
        *,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for segment, results in segment_results:
            for item in results:
                key = f"{item.get('doc_id') or item.get('case_id')}::{item.get('chunk_id')}"
                current = merged.get(key)
                item_score = float(item.get("score", 0.0) or 0.0)
                if current is None or item_score > float(current.get("score", 0.0) or 0.0):
                    previous_segments = list((current or {}).get("matched_segments") or [])
                    current = dict(item)
                    current["metadata"] = dict(item.get("metadata") or {})
                    current["matched_segments"] = previous_segments
                    merged[key] = current

                matched_segments = current.setdefault("matched_segments", [])
                if segment not in matched_segments:
                    matched_segments.append(segment)
                metadata = current.setdefault("metadata", {})
                metadata["matched_segments"] = list(matched_segments)

        merged_results = list(merged.values())
        for item in merged_results:
            matched_count = len(item.get("matched_segments") or [])
            if matched_count > 1:
                item["score"] = round(
                    min(1.0, float(item.get("score", 0.0) or 0.0) + min(0.1, 0.03 * (matched_count - 1))),
                    4,
                )

        merged_results.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
        results_list = merged_results[: max(1, top_k)]
        for rank, item in enumerate(results_list, start=1):
            item["rank"] = rank
        return results_list

    async def chunk_text(
        self, text: str, chunk_size: int = 500, overlap: int = 100
    ) -> List[str]:
        """
        텍스트 청킹

        Args:
            text: 원본 텍스트
            chunk_size: 청크 크기 (문자 수)
            overlap: 청크 간 겹침 크기

        Returns:
            청크 리스트
        """
        try:
            self.logger.info(f"텍스트 청킹: chunk_size={chunk_size}, overlap={overlap}")
            text = " ".join(text.split())
            if not text:
                return []

            if len(text) <= chunk_size:
                return [text]

            chunks: List[str] = []
            start = 0
            while start < len(text):
                end = min(len(text), start + chunk_size)
                chunks.append(text[start:end])
                if end >= len(text):
                    break
                start = max(end - overlap, start + 1)
            return chunks
        except Exception as e:
            self.logger.error(f"청킹 실패: {str(e)}")
            raise RetrievalError(f"청킹 실패: {str(e)}") from e

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        텍스트 임베딩

        Args:
            texts: 텍스트 리스트

        Returns:
            임베딩 벡터 리스트
        """
        try:
            self.logger.info(f"임베딩 생성: {len(texts)}개 텍스트")
            return self._get_vectorstore().embed_texts(texts)
        except Exception as e:
            self.logger.error(f"임베딩 실패: {str(e)}")
            raise RetrievalError(f"임베딩 실패: {str(e)}") from e

    async def index_documents(
        self,
        documents: List[Dict[str, Any]],
        rebuild: bool = False,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        문서 인덱싱

        Args:
            documents: 문서 리스트 (각 문서는 'id', 'text', 'metadata' 포함)
            rebuild: 기존 인덱스 재구축 여부

        Returns:
            인덱싱 결과 메타데이터
        """
        try:
            self.logger.info(f"문서 인덱싱 시작: {len(documents)}개 문서")
            result = self._index_documents_internal(
                documents,
                rebuild=rebuild,
                collection_name=collection_name,
            )
            self.logger.info(
                f"문서 인덱싱 완료: indexed={result['indexed_count']}, chunk={result['chunk_count']}"
            )
            if collection_name and collection_name != self.default_collection_name:
                self.logger.info(
                    "collection_name=%s is accepted for contract compatibility but the runtime store uses the default collection",
                    collection_name,
                )
            return result
        except Exception as e:
            self.logger.error(f"인덱싱 실패: {str(e)}")
            raise RetrievalError(f"인덱싱 실패: {str(e)}") from e

    async def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
        topic_type: Optional[str] = None,
        request_segments: Optional[List[str]] = None,
        retrieval_policy: Optional[str] = None,
        snippet_max_chars: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        의미론적 검색

        Args:
            query: 검색 쿼리
            top_k: 상위 결과 개수
            threshold: 유사도 임계값

        Returns:
            검색 결과 리스트
        """
        try:
            self.logger.info(f"검색 시작: query='{query}', top_k={top_k}")

            collection_key = collection_name or self.default_collection_name
            store = self._get_vectorstore()

            if store.count(collection_key) == 0:
                self._bootstrap_from_samples(collection_key)

            effective_snippet_max_chars = max(120, int(snippet_max_chars or 140))
            segments = self._normalize_request_segments(query, request_segments)
            if len(segments) > 1:
                segment_results = []
                for segment in segments:
                    results_for_segment = store.query(
                        collection_name=collection_key,
                        query=segment,
                        top_k=top_k,
                        filters=filters or {},
                        threshold=threshold,
                        snippet_max_chars=effective_snippet_max_chars,
                    )
                    results_for_segment = self._apply_retrieval_policy(
                        results_for_segment,
                        topic_type=topic_type,
                        retrieval_policy=retrieval_policy,
                    )
                    segment_results.append((segment, results_for_segment))
                results = self._merge_segment_results(segment_results, top_k=top_k)
            else:
                results = store.query(
                    collection_name=collection_key,
                    query=query,
                    top_k=top_k,
                    filters=filters or {},
                    threshold=threshold,
                    snippet_max_chars=effective_snippet_max_chars,
                )
                results = self._apply_retrieval_policy(
                    results,
                    topic_type=topic_type,
                    retrieval_policy=retrieval_policy,
                )

            self.logger.info(f"검색 완료: {len(results)}개 결과")
            return results

        except Exception as e:
            self.logger.error(f"검색 실패: {str(e)}")
            raise RetrievalError(f"검색 실패: {str(e)}") from e


# 싱글톤
_retrieval_service = None


def get_retrieval_service() -> RetrievalService:
    """검색 서비스 인스턴스 반환"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service

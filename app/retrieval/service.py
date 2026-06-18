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


METADATA_SOFT_RERANK_WEIGHTS = {
    "legal_ref_ids": 0.08,
    "legal_ref_names": 0.06,
    "entity_texts": 0.04,
    "responsible_units": 0.03,
}
METADATA_SOFT_RERANK_KEY_TERM_WEIGHT = 0.01
METADATA_SOFT_RERANK_KEY_TERM_MAX = 0.04
METADATA_SOFT_RERANK_MAX_BOOST = 0.20


class RetrievalService:
    """검색 서비스"""

    def __init__(self):
        """초기화"""
        self.logger = pipeline_logger
        self.embedding_model = settings.EMBEDDING_MODEL
        self.vectorstore_path = settings.CHROMA_DB_PATH
        self.embedding_device = settings.EMBEDDING_DEVICE
        self.default_collection_name = settings.DEFAULT_CHROMA_COLLECTION
        self._vectorstore: Optional[ChromaVectorStore] = None
        self._hybrid = None  # HybridRetriever (lazy)

    def _get_vectorstore(self) -> ChromaVectorStore:
        if self._vectorstore is None:
            self._vectorstore = ChromaVectorStore(
                persist_directory=self.vectorstore_path,
                embedding_model_name=self.embedding_model,
                embedding_device=self.embedding_device,
            )
        return self._vectorstore

    def _get_hybrid(self):
        """Hybrid(BM25+Dense RRF) 리트리버 (lazy). BM25 인덱스는 첫 호출 시 빌드·캐시."""
        if self._hybrid is None:
            from app.retrieval.search.hybrid import HybridRetriever

            self._hybrid = HybridRetriever(self._get_vectorstore(), rrf_k=settings.RRF_K)
        return self._hybrid

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

        chunk_text = str(record.get("chunk_text", "")).strip()
        if chunk_text:
            return chunk_text

        return str(record.get("text", "")).strip()

    def _dedupe_strings(self, values: List[Any]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for value in values:
            text = " ".join(str(value or "").split())
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
        return normalized

    def _extract_signal_values(
        self,
        value: Any,
        *,
        keys: tuple[str, ...] = ("name", "text"),
    ) -> List[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return self._dedupe_strings([item for item in value.split("|") if item])

        if isinstance(value, dict):
            raw_items = [value]
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = [value]

        extracted: List[Any] = []
        for item in raw_items:
            if isinstance(item, dict):
                for key in keys:
                    if item.get(key):
                        extracted.append(item.get(key))
                        break
            else:
                extracted.append(item)
        return self._dedupe_strings(extracted)

    def _extract_legal_ref_signals(self, value: Any) -> tuple[List[str], List[str]]:
        if value is None:
            return [], []

        raw_items = value if isinstance(value, list) else [value]
        names: List[Any] = []
        law_ids: List[Any] = []
        for item in raw_items:
            if isinstance(item, dict):
                names.append(item.get("name"))
                law_ids.append(item.get("law_id"))
            else:
                names.append(item)

        return self._dedupe_strings(names), self._dedupe_strings(law_ids)

    def _extract_urgency_level(self, value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(str(value.get("level") or "").split())
        if isinstance(value, list):
            values = self._extract_signal_values(value, keys=("level", "name", "text"))
            return values[0] if values else ""
        return " ".join(str(value or "").split())

    def _extract_civil_category(self, record: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, str]:
        """BE1 시민 표시용 카테고리를 색인 메타데이터 형태로 표준화한다."""
        civil_category = record.get("civil_category")
        if not isinstance(civil_category, dict):
            civil_category = metadata.get("civil_category") if isinstance(metadata.get("civil_category"), dict) else {}

        primary = str(
            civil_category.get("primary")
            or record.get("civil_category_primary")
            or metadata.get("civil_category_primary")
            or ""
        ).strip()
        secondary = str(
            civil_category.get("secondary")
            or record.get("civil_category_secondary")
            or metadata.get("civil_category_secondary")
            or ""
        ).strip()
        source = str(
            civil_category.get("source")
            or record.get("civil_category_source")
            or metadata.get("civil_category_source")
            or ""
        ).strip()
        return {
            "primary": primary,
            "secondary": secondary,
            "source": source,
        }

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
        search_entity_texts = (
            self._extract_signal_values(
                record.get("entity_texts", metadata.get("entity_texts")),
                keys=("text", "name"),
            )
            or entity_texts
        )
        legal_ref_names, legal_ref_ids = self._extract_legal_ref_signals(
            record.get("legal_refs", metadata.get("legal_refs"))
        )
        legal_ref_names = legal_ref_names or self._extract_signal_values(
            record.get("legal_ref_names", metadata.get("legal_ref_names")),
            keys=("name", "text"),
        )
        legal_ref_ids = legal_ref_ids or self._extract_signal_values(
            record.get("legal_ref_ids", metadata.get("legal_ref_ids")),
            keys=("law_id", "id", "text", "name"),
        )
        key_terms = self._extract_signal_values(
            record.get("key_terms", metadata.get("key_terms")),
            keys=("term", "text", "name"),
        )
        responsible_unit_value = record.get(
            "responsible_unit",
            record.get(
                "responsible_units",
                metadata.get("responsible_unit", metadata.get("responsible_units")),
            ),
        )
        responsible_units = self._extract_signal_values(
            responsible_unit_value,
            keys=("name", "unit", "text"),
        )
        responsible_unit_items = (
            responsible_unit_value
            if isinstance(responsible_unit_value, list)
            else [responsible_unit_value]
        )
        responsible_unit_sources = self._dedupe_strings([
            item.get("source")
            for item in responsible_unit_items
            if isinstance(item, dict)
        ])
        explicit_responsible_unit_sources = self._extract_signal_values(
            record.get(
                "responsible_units_source",
                metadata.get("responsible_units_source"),
            ),
            keys=("source", "name", "text"),
        )
        responsible_unit_sources = responsible_unit_sources or explicit_responsible_unit_sources
        if responsible_units and not responsible_unit_sources and "responsible_unit" in record:
            responsible_unit_sources = ["be1_structured"]
        responsible_units_source = responsible_unit_sources[0] if responsible_unit_sources else ""
        responsible_unit_confidences = [
            float(item["confidence"])
            for item in responsible_unit_items
            if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
        ]
        if responsible_unit_confidences:
            responsible_units_confidence = responsible_unit_confidences[0]
        else:
            raw_conf = record.get(
                "responsible_units_confidence",
                metadata.get("responsible_units_confidence"),
            )
            try:
                responsible_units_confidence = float(raw_conf) if raw_conf not in (None, "") else 0.0
            except (TypeError, ValueError):
                responsible_units_confidence = 0.0
        urgency_value = record.get(
            "urgency",
            record.get("urgency_level", metadata.get("urgency", metadata.get("urgency_level"))),
        )
        urgency_level = self._extract_urgency_level(urgency_value)
        civil_category = self._extract_civil_category(record, metadata)

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
            "search_entity_texts": search_entity_texts,
            "legal_ref_names": legal_ref_names,
            "legal_ref_ids": legal_ref_ids,
            "key_terms": key_terms,
            "responsible_units": responsible_units,
            "responsible_units_source": responsible_units_source,
            "responsible_units_confidence": responsible_units_confidence,
            "civil_category_primary": civil_category["primary"],
            "civil_category_secondary": civil_category["secondary"],
            "civil_category_source": civil_category["source"],
            "urgency_level": urgency_level,
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
        safe_documents = [
            record
            for record in documents
            if isinstance(record, dict) and not self._is_pii_unsafe_record(record)
        ]
        valid_document_count = len(
            [record for record in documents if isinstance(record, dict)]
        )
        skipped_pii_count = valid_document_count - len(safe_documents)
        normalized_documents = [
            self._normalize_record(record, index=index)
            for index, record in enumerate(safe_documents)
        ]
        safe_normalized_documents = [
            record
            for record in normalized_documents
            if str(record.get("chunk_text") or "").strip()
        ]
        skipped_empty_count = len(normalized_documents) - len(safe_normalized_documents)

        store = self._get_vectorstore()
        collection_key = collection_name or self.default_collection_name
        if rebuild:
            store.reset_collection(collection_key)

        result = store.upsert_records(collection_key, safe_normalized_documents)
        return {
            "indexed_count": int(result.get("indexed_count", 0)),
            "chunk_count": int(result.get("chunk_count", 0)),
            "index_name": collection_key,
            "rebuild": rebuild,
            "records": result.get("records", []),
            "skipped_pii_count": skipped_pii_count,
            "skipped_empty_count": skipped_empty_count,
        }

    def _is_pii_unsafe_record(self, record: Dict[str, Any]) -> bool:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        needs_review = record.get("needs_review", metadata.get("needs_review"))
        if isinstance(needs_review, str):
            needs_review = needs_review.strip().lower() in {"1", "true", "yes", "y"}
        if bool(needs_review):
            return True

        status = str(record.get("pii_status") or metadata.get("pii_status") or "").strip().upper()
        return status in {"REVIEW", "QUARANTINED"}

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
        parts = [" ".join(part.split()) for part in chunk_text.splitlines() if part.strip()]
        text = " ".join(parts)
        if len(text) <= max_length:
            return text
        if len(parts) > 1:
            separator = " | "
            budget = max(12, (max_length - len(separator) * (len(parts) - 1)) // len(parts))
            rendered = [
                part if len(part) <= budget else part[: max(1, budget - 3)].rstrip() + "..."
                for part in parts
            ]
            return separator.join(rendered)[:max_length].rstrip()
        tail_size = max(24, max_length // 2)
        head_size = max(24, max_length - tail_size - 5)
        return f"{text[:head_size].rstrip()} ... {text[-tail_size:].lstrip()}"

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

        # 4요소 구조화 쿼리(\n 구분)는 분할하지 않고 단일 임베딩으로 검색
        # 쉼표 분할은 의미 맥락을 파괴하여 검색 품질을 저하시킴 (issue #255)
        if "\n" in str(query or ""):
            return []

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
        """topic/policy 메타데이터(라우팅 trace)만 부착한다.

        과거에는 admin_policy/field_ops 정책에서 키워드 매칭 시 +0.04 점수 부스트를
        적용했으나, V3 100쿼리 평가에서 부스트가 nDCG@10 −0.018, R@10 −0.024로
        순위 품질을 악화시키는 것이 확인되어 제거했다. (#263,
        reports/retrieval/v3/risk3c_policy_boost_impact.json)
        """
        policy = str(retrieval_policy or "general").strip() or "general"
        for item in results:
            metadata = item.setdefault("metadata", {})
            metadata["retrieval_policy"] = policy
            if topic_type:
                metadata["topic_type"] = topic_type
        return results

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

    def _normalize_query_signals(
        self,
        query_signals: Optional[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        if not isinstance(query_signals, dict):
            return {}

        normalized: Dict[str, List[str]] = {}
        for field in (
            "entity_texts",
            "legal_ref_names",
            "legal_ref_ids",
            "key_terms",
            "responsible_units",
        ):
            values = self._extract_signal_values(query_signals.get(field))
            if values:
                normalized[field] = values
        return normalized

    def _overlap_count(self, left: List[str], right: List[str]) -> int:
        left_set = {str(item).casefold() for item in left if str(item).strip()}
        right_set = {str(item).casefold() for item in right if str(item).strip()}
        return len(left_set.intersection(right_set))

    def _metadata_soft_boost(
        self,
        query_signals: Dict[str, List[str]],
        item: Dict[str, Any],
    ) -> float:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        boost = 0.0

        for field, weight in METADATA_SOFT_RERANK_WEIGHTS.items():
            candidate_values = self._extract_signal_values(metadata.get(field))
            if self._overlap_count(query_signals.get(field, []), candidate_values) > 0:
                boost += weight

        key_term_overlap = self._overlap_count(
            query_signals.get("key_terms", []),
            self._extract_signal_values(metadata.get("key_terms")),
        )
        boost += min(
            METADATA_SOFT_RERANK_KEY_TERM_MAX,
            METADATA_SOFT_RERANK_KEY_TERM_WEIGHT * key_term_overlap,
        )
        return min(METADATA_SOFT_RERANK_MAX_BOOST, boost)

    def _apply_metadata_soft_rerank(
        self,
        results: List[Dict[str, Any]],
        query_signals: Optional[Dict[str, List[str]]],
    ) -> List[Dict[str, Any]]:
        if not query_signals or not any(query_signals.values()):
            return results

        reranked: List[Dict[str, Any]] = []
        for item in results:
            updated = dict(item)
            updated["metadata"] = dict(item.get("metadata") or {})
            boost = self._metadata_soft_boost(query_signals, updated)
            base_score = float(updated.get("score", 0.0) or 0.0)
            updated["score"] = round(base_score * (1.0 + boost), 6)
            reranked.append(updated)

        reranked.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
        for rank, item in enumerate(reranked, start=1):
            item["rank"] = rank
        return reranked

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
                    "collection_name=%s indexed with explicit Chroma collection",
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
        strategy: Optional[str] = None,
        grounding_filter: Optional[bool] = None,
        grounding_pool: Optional[int] = None,
        query_signals: Optional[Dict[str, Any]] = None,
        exclude_case_id: Optional[str] = None,
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
            grounding_on = (
                settings.GROUNDING_FILTER_ENABLED if grounding_filter is None else grounding_filter
            )
            effective_grounding_pool = max(
                top_k,
                int(grounding_pool or settings.GROUNDING_FILTER_POOL),
            )
            normalized_query_signals = self._normalize_query_signals(query_signals)
            metadata_rerank_on = bool(normalized_query_signals)

            # request_segments remain available to BE3 through routing_trace, but
            # they do not change BE2's fixed Hybrid candidate set or ranking.
            effective_strategy = strategy or settings.RETRIEVAL_STRATEGY
            use_hybrid = effective_strategy == "hybrid" and not (filters or {})
            retrieve_k = max(top_k, effective_grounding_pool) if grounding_on else top_k
            if metadata_rerank_on:
                retrieve_k = max(retrieve_k, settings.HYBRID_FANOUT)
            fanout = max(retrieve_k, settings.HYBRID_FANOUT) if use_hybrid else retrieve_k
            dense_results = store.query(
                collection_name=collection_key,
                query=query,
                top_k=fanout,
                filters=filters or {},
                threshold=threshold,
                snippet_max_chars=effective_snippet_max_chars,
            )
            if use_hybrid:
                try:
                    results = self._get_hybrid().search(
                        collection_key, query, retrieve_k, dense_results,
                        fanout=settings.HYBRID_FANOUT,
                    )
                except Exception as exc:  # 안전: Hybrid 실패 시 Dense로 폴백
                    self.logger.warning(f"Hybrid 검색 실패, Dense 폴백: {exc}")
                    results = dense_results[:retrieve_k]
            else:
                results = dense_results[:retrieve_k]

            if exclude_case_id:
                excluded = str(exclude_case_id).strip().upper()
                excluded = excluded.removeprefix("CASE-")

                def _is_current_case(item: Dict[str, Any]) -> bool:
                    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                    candidates = (
                        item.get("case_id"),
                        item.get("doc_id"),
                        metadata.get("case_id"),
                        metadata.get("source_id"),
                    )
                    return any(
                        str(value or "").strip().upper().removeprefix("CASE-") == excluded
                        for value in candidates
                    )

                results = [item for item in results if not _is_current_case(item)]

            results = self._apply_retrieval_policy(
                results,
                topic_type=topic_type,
                retrieval_policy=retrieval_policy,
            )
            results = self._apply_metadata_soft_rerank(results, normalized_query_signals)

            if grounding_on and results:
                results = await self._apply_grounding_filter(
                    query,
                    results[:effective_grounding_pool],
                    top_k,
                )
            elif metadata_rerank_on:
                results = results[: max(1, top_k)]

            self.logger.info(f"검색 완료: {len(results)}개 결과")
            return results

        except Exception as e:
            self.logger.error(f"검색 실패: {str(e)}")
            raise RetrievalError(f"검색 실패: {str(e)}") from e

    @staticmethod
    def _grounding_text(item: Dict[str, Any]) -> str:
        """grounding 필터 입력 텍스트: 본문(snippet) + 소관 분야/관할(category·region).

        cross_encoder_rerank._get_text와 동일 의도(같은 관련성 신호)."""
        body = str(item.get("snippet") or "")
        if not body:
            summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
            body = " ".join(
                part for part in (str(summary.get("observation") or ""), str(summary.get("request") or "")) if part
            )
        if not body:
            body = str(item.get("title") or "")
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        domain = " ".join(
            part for part in (str(meta.get("category") or ""), str(meta.get("region") or "")) if part
        )
        text = f"[{domain}] {body}".strip() if domain else body
        return text or str(item.get("case_id") or "")

    async def _apply_grounding_filter(
        self, query: str, results: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        """LLM 관련성 필터로 해로운(rel0) 선례를 근거에서 제거 (#305).

        통과 0개면 빈 리스트 반환 → 호출부(be3)에서 "유사 사례 없음" 폴백.
        """
        from app.retrieval.grounding_filter import (
            filter_by_relevance,
            filter_by_scores,
            score_relevance,
            score_relevance_batch,
        )

        model = settings.GROUNDING_FILTER_MODEL or settings.OLLAMA_MODEL
        pool = list(results)[: settings.GROUNDING_FILTER_POOL]
        texts = [self._grounding_text(item) for item in pool]
        scores = await score_relevance_batch(query, texts, model=model)

        if scores is not None:
            kept = filter_by_scores(
                pool,
                scores,
                min_score=settings.GROUNDING_FILTER_MIN_SCORE,
                top_k=top_k,
            )
            filter_mode = "batch"
        else:
            async def score_fn(q: str, text: str) -> Optional[int]:
                return await score_relevance(q, text, model=model)

            kept = await filter_by_relevance(
                query,
                pool,
                get_text=self._grounding_text,
                score_fn=score_fn,
                min_score=settings.GROUNDING_FILTER_MIN_SCORE,
                rerank_pool=settings.GROUNDING_FILTER_POOL,
                top_k=top_k,
                max_concurrency=settings.GROUNDING_FILTER_MAX_CONCURRENCY,
            )
            filter_mode = "per_item_fallback"
        filtered = [item for item, _ in kept]
        self.logger.info(
            f"grounding 필터({filter_mode}): {len(results)}→{len(filtered)}개 "
            "(해로운 선례 제거)"
        )
        return filtered


# 싱글톤
_retrieval_service = None


def get_retrieval_service() -> RetrievalService:
    """검색 서비스 인스턴스 반환"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service

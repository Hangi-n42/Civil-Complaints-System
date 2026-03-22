# Week 2 BE2 - ChromaDB 컬렉션/필터 동작 점검 기록

기준 이슈: #25  
작성일: 2026-03-22

## 1) 목적

Week2 계약의 검색 메타데이터 키(`category`, `region`, `created_at`, `entity_labels`) 기준으로
ChromaDB 컬렉션 조회 필터가 재현 가능하게 동작하는지 점검한다.

## 2) 실행 방법

```bash
c:/Projects/AI-Civil-Affairs-Systems/.venv/Scripts/python.exe scripts/check_chromadb_filters.py
```

옵션:

- `--persist-dir`: ChromaDB 저장 경로 지정
- `--collection`: 점검 컬렉션명 지정
- `--output`: 점검 리포트 경로 지정
- `--no-reset`: 기존 컬렉션 유지

## 3) 산출물

- 점검 스크립트: `scripts/check_chromadb_filters.py`
- 점검 모듈: `app/retrieval/vectorstores/chroma_validation.py`
- 점검 리포트(기본): `logs/evaluation/week2_be2_chromadb_filter_report.json`

## 4) 점검 항목

- category exact match
- region exact match
- created_at exact match
- created_at range(`$gte`, `created_at_ts` 보조 필드 사용)
- entity_labels exact match

## 5) 판정 기준

- 각 점검 항목의 `actual_count >= expected_min` 이면 pass
- 모든 항목 pass 시 report `status = passed`

# 🏛️ AI-Civil-Affairs-Systems

**민원 담당자를 위한 LLM-Chain 기반 On-Device 검색·분류 시스템**

- 📋 프로젝트: 졸업 작품 / 팀 프로젝트
- 👥 팀: 4명 (BE1, FE, BE2, BE3)
- ⏰ 기간: 8주 (M1~M4)
- 🔒 특징: 온디바이스 실행, 보안/프라이버시 중심
- 🚀 현재 상태: M2 Week 3 진행중 (index-search E2E + 모델 벤치마크)

---

## 📖 프로젝트 개요

### 목표
- 로컬 머신에서 민원 데이터를 구조화하고 검색/질의응답 가능한 형태로 변환
- 주 데이터 소스: AIHub 공공 민원 상담 LLM 사전학습 및 Instruction Tuning 데이터 (`dataSetSn=71852`)
- Ollama + ChromaDB 기반 온디바이스 RAG 시스템 구축
- 보안과 프라이버시를 중심으로 한 엔드-투-엔드 파이프라인 구현

### 핵심 기능 (In Scope)
1. 문서 입수: CSV/JSON 배치 + 수동 입력
2. 구조화: Observation/Result/Request/Context 4요소 추출
3. 엔티티 추출: LOCATION/TIME/FACILITY/HAZARD/ADMIN_UNIT
4. 검색: 임베딩 + 벡터 인덱스 기반 시맨틱 검색
5. QA: 근거 citation 포함 RAG 응답 생성

### 기술 스택
- API: FastAPI
- UI: Streamlit
- LLM 서빙: Ollama (로컬 모델 벤치마크 후 선정)
- 임베딩: BAAI/bge-m3 (대안 KoSimCSE)
- 벡터DB: ChromaDB
- 언어: Python 3.11+

---

## 🎯 진행 상황

### ✅ Completed
- M1 (W1~W2) 완료
  - PRD/MVP/WBS/계약 문서 정리
  - ingest-structure-validate E2E 안정화
  - 샘플 50건+ 처리 및 스키마 통과율 목표 달성
  - Week2 이슈 기반 주요 결함 수정 완료

### 🚀 In Progress (M2 W3)
- index-search E2E 고도화
- 평가셋(500건) 및 모델 벤치마크 실행 체계 운영
- 검색 지표(Recall@K, latency) 측정 및 리포트 정리
- 역할별 매뉴얼 v1.1 최신화 반영

### ⏳ Next (M2 W4)
- 단일 RAG baseline 확정
- `/qa` JSON 응답 안정화(answer/citations/confidence/limitations)
- Gate A 지표 확정(Recall@5, 4요소 F1, citation 정합성, latency)

---

## 📁 폴더 구조

```text
AI-Civil-Affairs-Systems/
├── app/                    # 애플리케이션 소스코드
│   ├── api/                # FastAPI 서버
│   ├── core/               # 설정, 로깅, 예외
│   ├── ingestion/          # 데이터 입수
│   ├── structuring/        # 데이터 구조화
│   ├── retrieval/          # 검색 시스템
│   ├── generation/         # RAG 응답 생성
│   ├── ui/                 # Streamlit UI
│   └── tests/              # 테스트 코드
├── configs/                # 설정 파일
├── data/                   # 데이터 관리
├── docs/                   # 문서
├── logs/                   # 로그 저장
├── reports/                # 평가/분석 보고서
├── schemas/                # JSON 스키마
├── scripts/                # 실행 스크립트
└── requirements.txt        # 의존성
```

자세한 구조는 [docs/00_overview/folder_structure.md](docs/00_overview/folder_structure.md) 참조.

---

## 🚀 빠른 시작

### 1) 환경 설정
```bash
git clone https://github.com/Hangi-n42/AI-Civil-Affairs-Systems.git
cd AI-Civil-Affairs-Systems

python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
# source venv/bin/activate

pip install -r requirements.txt
```

### 2) Ollama 준비
```bash
# Ollama 설치 후
ollama serve
```

### 3) API/UI 실행
```bash
python scripts/run_api.py
python scripts/run_ui.py
```

확인:
- API 문서: http://localhost:8000/docs
- UI: http://localhost:8501

---

## 📦 Week 3 실행 핵심

### 평가셋 생성
```bash
python scripts/generate_week3_benchmark_cases_500.py \
  --input data/samples/initial_sample_20.json \
  --output docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --target 500 \
  --seed 42
```

### 모델 벤치마크 실행 예시
```bash
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model aihub_baseline
```

상세 절차는 [docs/40_delivery/week3/README.md](docs/40_delivery/week3/README.md) 참조.

---

## 📚 주요 문서

| 문서 | 설명 |
|------|------|
| [docs/00_overview/prd.md](docs/00_overview/prd.md) | 전체 프로젝트 명세 |
| [docs/00_overview/mvp_scope.md](docs/00_overview/mvp_scope.md) | MVP 범위 |
| [docs/00_overview/wbs_8weeks_v2_updated.md](docs/00_overview/wbs_8weeks_v2_updated.md) | 8주 WBS/마일스톤 |
| [docs/00_overview/folder_structure.md](docs/00_overview/folder_structure.md) | 폴더 구조 |
| [docs/10_contracts/api/api_spec.md](docs/10_contracts/api/api_spec.md) | API 명세 |
| [docs/10_contracts/schema/schema_contract.md](docs/10_contracts/schema/schema_contract.md) | 스키마 계약 |
| [docs/10_contracts/interfaces/week3/week3_common_interface.md](docs/10_contracts/interfaces/week3/week3_common_interface.md) | Week3 공통 인터페이스 |
| [docs/40_delivery/week3/README.md](docs/40_delivery/week3/README.md) | Week3 전달 문서 |
| [docs/30_manuals/be1_manual.md](docs/30_manuals/be1_manual.md) | BE1 매뉴얼(v1.1) |
| [docs/30_manuals/be2_manual.md](docs/30_manuals/be2_manual.md) | BE2 매뉴얼(v1.1) |
| [docs/30_manuals/be3_manual.md](docs/30_manuals/be3_manual.md) | BE3 매뉴얼(v1.1) |
| [docs/30_manuals/fe_manual.md](docs/30_manuals/fe_manual.md) | FE 매뉴얼(v1.1) |

---

## 👥 팀 구성

| 역할 | 담당 | 주요 책임 |
|------|------|-----------|
| BE1 (팀장) | 현기 | 데이터 파이프라인, 구조화, 평가, 발표 총괄 |
| FE | 도훈 | UI/UX, 검색/QA 화면, 데모 흐름 |
| BE2 | 민건 | 임베딩/벡터DB/검색/검색평가 |
| BE3 | 현석 | API/LLM/RAG/파싱/성능 안정화 |

---

## 🗓️ 마일스톤

| 마일스톤 | 기간 | 상태 | 핵심 목표 |
|---------|------|------|-----------|
| M1 | W1~W2 | ✅ 완료 | 기준선 고정 + ingestion/structuring/validation 안정화 |
| M2 | W3~W4 | 🚀 진행중 | index-search E2E + 단일 RAG baseline 확정 |
| M3 | W5~W6 | ⏳ 계획 | Adaptive RAG 1차/2차 적용 |
| M4 | W7~W8 | ⏳ 계획 | 품질 튜닝 + 데모/발표 산출물 동결 |

---

## 🔗 GitHub

- 저장소: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems
- 이슈: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues
- PR: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/pulls

---

## 📝 라이선스

대학 졸업 프로젝트 (비공개)

---

**Last Updated**: 2026-03-27  
**Status**: 🚀 M2 Week 3 진행중

# 🏛️ AI-Civil-Affairs-Systems

**민원 담당자를 위한 LLM-Chain 기반 On-Device 검색·분류 시스템**

- 📋 **프로젝트**: 졸업 작품 / 팀 프로젝트
- 👥 **팀**: 4명 (BE1, FE, BE2, BE3)
- ⏰ **기간**: 8주 (M1~M4)
- 🔒 **특징**: 온디바이스 실행, 보안/프라이버시 중심
- 🚀 **상태**: M1 Week 1 (폴더 구조 스캐폰딩 완료)

---

## 📖 프로젝트 개요

### 목표
- 로컬 머신에서 자동으로 민원 데이터를 구조화하고 검색 가능하게 변환
- 주 데이터 소스: AIHub 공공 민원 상담 LLM 사전학습 및 Instruction Tuning 데이터 (`dataSetSn=71852`)
- Ollama + ChromaDB를 활용한 온디바이스 RAG 시스템 구축
- 보안과 프라이버시를 중심으로 한 엔드-투-엔드 파이프라인

### 주요 기능
1. **📤 문서 입수**: CSV/JSON 업로드, 자동 정제
2. **🔨 구조화**: AI 기반 4요소 추출 (요청인, 피청구인, 청구 내용, 사유)
3. **📊 인덱싱**: 의미론적 검색 (벡터화 + 임베딩)
4. **🔍 검색**: 자연어 검색 쿼리
5. **💬 QA**: RAG 기반 질의응답 (근거 citation 포함)

### 기술 스택
- **API**: FastAPI
- **UI**: Streamlit
- **LLM**: Ollama + Qwen2.5 7B Instruct
- **임베딩**: BAAI/bge-m3
- **벡터DB**: ChromaDB
- **언어**: Python 3.11.9

---

## 🎯 진행 상황

### ✅ Completed (M1 Week 1)
- [x] **기획 문서**: PRD, MVP 범위, 8주 WBS 완료
- [x] **기술 명세**: API 명세, 데이터 스키마 계약 완료
- [x] **팀 구성**: 역할 배치 (BE1, FE, BE2, BE3) 완료
- [x] **역할별 매뉴얼**: 4개 매뉴얼 작성 완료
- [x] **GitHub 이슈**: Week 1 이슈 5개 원격 생성 완료
- [x] **Priority 1**: 프로젝트 스캐폰딩 생성 완료 ✨
  - 폴더 구조 (40+ 디렉토리)
  - FastAPI 기본 골격
  - 5개 모듈 skeleton (ingestion, structuring, retrieval, generation, ui)
  - 설정/로깅/예외 처리
  - Streamlit 3탭 UI
  - 샘플 데이터 + 스키마

### ⏳ In Progress (M1 Week 1~2)
- [ ] **Priority 2**: 샘플 데이터셋 + 데이터 정제 규칙 (BE1, BE3)
- [ ] **Priority 3**: 벡터DB + Ollama 테스트 (BE2, BE3)
- [ ] **Priority 4**: Streamlit UI 프로토타입 (FE)
- [ ] **Priority 5**: 검증 규칙 + 성능 기준선 (BE3)

### 📋 Planned (M1 Week 2+)
- [ ] Week 2~8 이슈 생성
- [ ] 실제 코드 구현 (각 Priority별)
- [ ] 통합 테스트
- [ ] 성능 벤치마크
- [ ] 발표 준비

---

## 📁 폴더 구조

```
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
├── data/                   # 데이터 관리
│   ├── raw/                # 원본
│   ├── interim/            # 중간 산출물
│   ├── processed/          # 최종 처리
│   ├── annotations/        # 라벨링
│   └── samples/            # 샘플 데이터
├── configs/                # 설정 파일
├── schemas/                # JSON 스키마
├── scripts/                # 실행 스크립트
├── logs/                   # 로그 저장
├── artifacts/              # 발표 자료
├── docs/                   # 문서
└── requirements.txt        # 의존성
```

자세한 구조는 [PRIORITY_1_COMPLETED.md](PRIORITY_1_COMPLETED.md) 참조.

---

## 🚀 빠른 시작

### 1️⃣ 환경 설정
```bash
# 저장소 클론
git clone https://github.com/Hangi-n42/AI-Civil-Affairs-Systems.git
cd AI-Civil-Affairs-Systems

# 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows

# .env 파일 생성
cp .env.example .env

# 의존성 설치
pip install -r requirements.txt
```

### 2️⃣ Ollama 설치 (로컬 LLM)
```bash
# Ollama 다운로드 및 설치 (https://ollama.ai)
# 모델 다운로드
ollama pull qwen2.5:7b-instruct

# Ollama 서버 시작
ollama serve
# (별도 터미널에서 실행 유지)
```

### 3️⃣ API 서버 시작
```bash
python scripts/run_api.py
# 또는
uvicorn app.api.main:app --reload
```

**확인**: 
- API 문서: http://localhost:8000/docs
- 헬스 체크: `curl http://localhost:8000/health`

### 4️⃣ UI 시작 (별도 터미널)
```bash
python scripts/run_ui.py
# 또는
streamlit run app/ui/Home.py
```

**확인**: http://localhost:8501

---

## 📚 주요 문서

| 문서 | 설명 |
|------|------|
| [docs/prd_draft.md](docs/prd_draft.md) | 전체 프로젝트 명세 |
| [docs/mvp_scope.md](docs/mvp_scope.md) | MVP 필수/권장/제외 기능 |
| [docs/wbs_8weeks.md](docs/wbs_8weeks.md) | 8주 마일스톤 및 역할별 작업 |
| [docs/api_spec.md](docs/api_spec.md) | API 엔드포인트 명세 |
| [docs/schema_contract.md](docs/schema_contract.md) | 데이터 스키마 계약 |
| [docs/folder_structure_draft.md](docs/folder_structure_draft.md) | 폴더 구조 설계 |
| [docs/be1_manual.md](docs/be1_manual.md) | BE1 역할 매뉴얼 |
| [docs/fe_manual.md](docs/fe_manual.md) | FE 역할 매뉴얼 |
| [docs/be2_manual.md](docs/be2_manual.md) | BE2 역할 매뉴얼 |
| [docs/be3_manual.md](docs/be3_manual.md) | BE3 역할 매뉴얼 |
| [NEXT_TASKS.md](NEXT_TASKS.md) | 다음 우선순위 작업 |
| [PRIORITY_1_COMPLETED.md](PRIORITY_1_COMPLETED.md) | Priority 1 완료 현황 |

---

## 👥 팀 구성

| 역할 | 이름 | 책임 |
|------|------|------|
| **BE1** (팀장) | 현기 | 데이터 파이프라인, 구조화, 평가, 발표 |
| **FE** | 도훈 | UI/UX, 데모 |
| **BE2** | 민건 | 검색, 벡터DB, RAG API |
| **BE3** | 현석 | 검증, 파싱, 성능, 안정성 |

자세한 책임은 각 역할 매뉴얼 참조.

---

## 🗓️ 마일스톤

| 마일스톤 | 기간 | 목표 |
|---------|------|------|
| **M1** | W1~W2 | 기술 선택, 프로토타입 (ingestion, structuring) |
| **M2** | W3~W4 | RAG 파이프라인 완성 (retrieval, generation) |
| **M3** | W5~W6 | UI 통합 및 성능 최적화 |
| **M4** | W7~W8 | 최종 평가, 발표 준비 |

---

## 🔗 GitHub

- **저장소**: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems
- **이슈**: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues
- **Week 1 이슈**: 
  - #2: [Week 1][Common] MVP 기준선 정리 및 인터페이스 1차 동결
  - #3: [Week 1][BE1] 데이터 입력 규격·정제 규칙·구조화 평가 기준 초안
  - #4: [Week 1][BE2] 임베딩·벡터DB 후보 비교 및 Ollama/RAG API 입력 구조
  - #5: [Week 1][BE3] 스키마 검증 규칙·JSON 파싱·성능/OOM 기준 초안
  - #6: [Week 1][FE] 업로드·검색·챗 화면 와이어프레임 및 데모 사용자 흐름

---

## 📈 DORA Metrics 자동화

GitHub Actions로 DORA 4대 지표를 자동 집계합니다.

- **워크플로**: `.github/workflows/dora-metrics.yml`
  - 매일 00:00 UTC 자동 실행
  - 수동 실행 시 `window_days`, `incident_label` 입력 가능
- **집계 스크립트**: `.github/scripts/calc_dora_metrics.mjs`
- **산출물**: Actions Artifact `dora-metrics` (`artifacts/dora/dora_metrics_latest.json`)

측정 정의(현재 적용 기준):
- Lead Time for Changes: 병합된 PR의 `첫 커밋 시각 -> merge 시각`
- Deployment Frequency: 기본 브랜치 기준 `성공한 GitHub Deployment` 수/일
- Mean Time to Recovery: `incident` 라벨 이슈의 `생성 -> 종료` 시간
- Change Failure Rate: `(실패 Deployment) / (성공+실패 Deployment)`

배포 이벤트는 아래 워크플로로 자동 기록됩니다.
- `.github/workflows/deploy-production.yml`
  - `main` push 또는 수동 실행 시 deployment 생성
  - smoke check(`python -m compileall app scripts`) 성공/실패를 deployment status로 기록

운영 규칙:
- 장애 이슈는 `incident` 라벨(또는 실행 시 지정 라벨)로 관리
- 배포 실패를 CFR에 반영하려면 `deploy-production` 실패 케이스가 누락되지 않도록 유지

---

## 💡 주요 특징

### 🔒 보안 & 프라이버시
- 온디바이스 실행 (클라우드 의존 X)
- 로컬 머신에서만 데이터 처리
- PII 마스킹 지원

### ⚡ 성능
- BGE-m3 임베딩 모델 (1024차원)
- ChromaDB 벡터 인덱싱
- Ollama 로컬 LLM (GPU 가능)

### 📊 평가 기반 설계
- 구조화 정확도 평가 (Precision, Recall, F1)
- 검색 성능 평가 (MRR, NDCG, MAP@k)
- QA 품질 평가 (BLEU, ROUGE, F1)

### 🎯 조직화된 개발
- GitHub 이슈 기반 작업 추적
- 역할별 명확한 책임 분담
- 통합 스크립트로 빌드/테스트 자동화

---

## 📝 라이선스

대학 졸업 프로젝트 (비공개)

---

## 📞 문의

프로젝트 진행 중 이슈는 GitHub Issues에서 추적합니다.

---

**Last Updated**: 2026-03-11  
**Status**: 🚀 M1 Week 1 - Priority 1 완료

"""
프로젝트 구조 스캐폴딩 생성 완료

이 README는 초기 프로젝트 구조가 생성된 후 다음 단계를 안내한다.
"""

# 🏗️ AI-Civil-Affairs-Systems 프로젝트 구조 생성 완료

## ✅ 완료된 작업 (Priority 1)

### 1️⃣ 폴더 구조 생성 ✅
```
app/
├── api/              # FastAPI 진입점
├── core/             # 공통 설정, 로깅, 예외
├── ingestion/        # 데이터 입수
├── structuring/      # 구조화
├── retrieval/        # 검색
├── generation/       # 응답 생성
├── ui/               # Streamlit UI
└── tests/            # 테스트

data/                 # 데이터 저장
├── raw/              # 원본
├── interim/          # 중간 산출물
├── processed/        # 최종 처리된 데이터
├── annotations/      # 레이블링
└── samples/          # 샘플 데이터

configs/              # 설정 파일
schemas/              # JSON 스키마
scripts/              # 실행 스크립트
logs/                 # 로그 파일
artifacts/            # 발표 자료
```

### 2️⃣ FastAPI 기본 골격 ✅
- **app/api/main.py**: `/health` 엔드포인트, CORS 설정, 앱 초기화
- **app/core/config.py**: 환경 변수 기반 설정 관리
- **app/core/logging.py**: 로깅 설정 (파일 + 콘솔)
- **app/core/exceptions.py**: 사용자 정의 예외 클래스

### 3️⃣ 각 모듈 Skeleton 구현 ✅

#### Ingestion (app/ingestion/service.py)
- `load_csv()`, `load_json()`
- `clean_text()`, `mask_pii()`
- `deduplicate()`
- `process()` - 종합 파이프라인

#### Structuring (app/structuring/service.py)
- `extract_four_elements()` - 4요소 추출
- `extract_entities()` - 개체명 인식
- `validate_schema()` - 스키마 검증
- `compute_confidence_score()` - 신뢰도 점수
- `structure()` - 종합 파이프라인

#### Retrieval (app/retrieval/service.py)
- `chunk_text()` - 청킹
- `embed_texts()` - 임베딩
- `index_documents()` - 인덱싱
- `search()` - 의미론적 검색

#### Generation (app/generation/service.py)
- `call_ollama()` - Ollama LLM 호출
- `build_rag_prompt()` - RAG 프롬프트 구성
- `parse_json_response()` - JSON 파싱
- `build_citations()` - Citation 생성
- `generate_qa()` - QA 응답 생성

#### UI (app/ui/Home.py)
- 📤 문서 업로드 탭
- 🔍 검색 탭
- 💬 챗봇 탭
- 더미 데이터 + 실행 가능한 구조

### 4️⃣ Dependencies & Configuration ✅
- **requirements.txt**: 모든 필수 패키지 목록
- **configs/base.yaml**: 기본 설정
- **configs/local.yaml**: 로컬 개발 설정
- **configs/models.yaml**: 모델 설정
- **.env.example**: 환경 변수 샘플

### 5️⃣ 실행 스크립트 ✅
- **scripts/run_api.py**: FastAPI 서버 실행
- **scripts/run_ui.py**: Streamlit UI 실행
- **scripts/build_index.py**: 벡터 인덱스 빌드 (skeleton)
- **scripts/evaluate_*.py**: 평가 스크립트 (skeleton)

### 6️⃣ 샘플 데이터 & 스키마 ✅
- **data/samples/sample_cases.json**: 3개 샘플 민원 데이터
- **schemas/civil_case.schema.json**: 구조화된 민원 데이터 스키마

---

## 🚀 다음 단계 (Priority 2~5)

### Priority 2: 샘플 데이터셋 + 데이터 정제 규칙
**담당**: BE1 (현기) + BE3 (현석)  
**작업**:
1. `data/raw/`에 샘플 민원 20~50건 수집
2. `app/ingestion/service.py`에 실제 정제 로직 구현
3. `app/structuring/service.py`에 4요소 추출 로직 구현
4. 구조화 파이프라인 엔드-투-엔드 테스트

### Priority 3: 벡터DB 후보 비교 + Ollama 테스트
**담당**: BE2 (민건) + BE3 (현석)  
**작업**:
1. ChromaDB/Milvus 로컬 설치 및 성능 테스트
2. BGE-m3 임베딩 모델 다운로드 및 테스트
3. Ollama + Qwen2.5 7B 실행 테스트
4. `app/retrieval/service.py`에 실제 임베딩/검색 로직 구현
5. `app/generation/service.py`에 Ollama 호출 로직 구현

### Priority 4: Streamlit UI 와이어프레임 + 프로토타입
**담당**: FE (도훈) + BE2, BE3  
**작업**:
1. `app/ui/Home.py`의 3탭 UI를 더미 데이터로 테스트
2. FastAPI 백엔드와 연결
3. 와이어프레임 이미지/동영상 준비

### Priority 5: 검증 규칙 + 성능 기준선
**담당**: BE3 (현석) + 전체 팀  
**작업**:
1. Pydantic 모델로 스키마 검증 규칙 구현
2. 샘플 데이터 20건 수동 검증
3. 성능 벤치마크 (인제스트, 검색, QA 시간 측정)

---

## 🎯 즉시 실행 가능한 명령어

### 1. 환경 설정
```bash
# .env 파일 생성
cp .env.example .env

# 의존성 설치
pip install -r requirements.txt
```

### 2. API 서버 시작 (Ollama가 실행 중이어야 함)
```bash
python scripts/run_api.py
# 또는
uvicorn app.api.main:app --reload
```

브라우저에서 `http://localhost:8000/docs` 접속 → Swagger UI 확인

### 3. Streamlit UI 시작
```bash
python scripts/run_ui.py
# 또는
streamlit run app/ui/Home.py
```

브라우저에서 `http://localhost:8501` 접속

### 4. 헬스 체크
```bash
curl http://localhost:8000/health
```

---

## 📋 체크리스트 (Week 1 진행)

### Before Priority 2
- [ ] `.env` 파일 생성 및 설정
- [ ] `pip install -r requirements.txt` 실행
- [ ] Ollama 설치 및 `qwen2.5:7b-instruct` 모델 다운로드
- [ ] `python scripts/run_api.py` 실행 확인
- [ ] `curl http://localhost:8000/health` 200 응답 확인

### Priority 2 중
- [ ] `data/raw/samples.json`에 샘플 데이터 준비
- [ ] `app/ingestion/service.py` 실제 로직 구현
- [ ] `app/structuring/service.py` 4요소 추출 로직 구현
- [ ] 구조화 파이프라인 테스트

### Priority 3 중
- [ ] ChromaDB 또는 Milvus 선정
- [ ] `app/retrieval/service.py` 임베딩/검색 로직 구현
- [ ] `app/generation/service.py` Ollama 호출 로직 구현
- [ ] RAG 파이프라인 엔드-투-엔드 테스트

---

## 📚 참고 자료

- **아키텍처**: [docs/folder_structure_draft.md](../docs/folder_structure_draft.md)
- **API 명세**: [docs/api_spec.md](../docs/api_spec.md)
- **데이터 스키마**: [docs/schema_contract.md](../docs/schema_contract.md)
- **역할별 매뉴얼**: [docs/be1_manual.md](../docs/be1_manual.md) 등
- **GitHub 이슈**: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues

---

## 🔧 팁

### 로컬 개발
```bash
# 설정을 local.yaml로 오버라이드
DEBUG=true LOG_LEVEL=DEBUG python scripts/run_api.py
```

### 테스트
```bash
pytest app/tests/unit/
pytest app/tests/integration/
```

### 타입 검사
```bash
mypy app/
```

### 코드 포맷팅
```bash
black app/
flake8 app/
```

---

## 📞 문제 해결

### import 오류
`PYTHONPATH` 설정 확인:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Ollama 연결 오류
```bash
# Ollama 서버 실행 확인
curl http://localhost:11434/api/tags

# 모델 다운로드
ollama pull qwen2.5:7b-instruct
```

### ChromaDB 오류
```bash
# 기존 DB 제거 후 재시작
rm -rf data/chroma_db
```

---

**생성일**: 2026-03-11  
**작성자**: AI Copilot  
**다음 검토**: Week 1 종료 후 (2026-03-18)

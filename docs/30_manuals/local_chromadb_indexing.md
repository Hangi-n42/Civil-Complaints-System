# 로컬 ChromaDB 인덱싱 가이드

민원 원천데이터를 로컬 ChromaDB에 인덱싱하는 절차입니다.

---

## 1. 사전 준비

### 1.1. Ollama 모델 설치
구조화 LLM 모델을 받아둡니다.
```powershell
ollama pull exaone3.5:7.8b
ollama list   # exaone3.5:7.8b 확인
```

### 1.2. PyTorch (GPU 사용 시)
CUDA 지원 PyTorch가 설치되어 있어야 합니다.

```powershell
python -c "import torch; print(torch.cuda.is_available())"
```
- `True` → GPU 사용 가능
- `False` → CPU 모드로 실행하려면 `$env:EMBEDDING_DEVICE = "cpu"` 환경변수 추가

CUDA 12.1 기준 재설치:
```powershell
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 1.3. 데이터 위치
AI Hub 원천데이터를 아래 경로에 배치합니다.

```
data/Public_Civil_Service_LLM_Data/Training/01.원천데이터/
  ├── TS_국립아시아문화전당/
  ├── TS_중앙행정기관/
  └── TS_지방행정기관/
```

> ⚠️ 인덱싱 대상은 **`01.원천데이터` 하위**만 사용합니다. `02.라벨링데이터`(약 11만 개)는 인덱싱 대상이 아닙니다.

---

## 2. 실행 순서

### (선택) 이미 `data/chroma_db`가 준비된 경우: 인덱싱 생략하고 바로 검증
이미 `data/chroma_db`를 설치/복사해둔 상태라면, 인덱싱을 다시 돌리지 않아도 됩니다.

1) FastAPI 서버 기동 (터미널 1)
```powershell
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

2) 컬렉션 존재/건수 확인 (터미널 2)
```powershell
python -c "import chromadb; c=chromadb.PersistentClient(path='data/chroma_db').get_collection('civil_cases_v1'); print('count=', c.count())"
```

`count`가 1 이상이면, 이미 검색 가능한 상태입니다. 이어서 `http://127.0.0.1:8000/docs`에서 `/api/v1/search`를 호출해 결과가 나오는지 확인하세요.

### Step 1. FastAPI 서버 기동 (터미널 1)
```powershell
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```
시작 로그에서 `ChromaDB`, `Ollama` 경로가 출력되면 정상입니다.

> ⚠️ 환경변수(예: `EMBEDDING_DEVICE`)를 변경하면 **FastAPI 서버를 반드시 재시작**해야 합니다. 서버는 시작 시점에만 환경변수를 읽습니다.

### Step 2. 인덱싱 실행 (터미널 2)

**소규모 테스트 (50개로 검증, 권장)**
```powershell
python scripts/build_index.py `
  --input-dir ".\data\Public_Civil_Service_LLM_Data\Training\01.원천데이터\TS_국립아시아문화전당" `
  --limit 50
```

**전체 인덱싱 (단일 기관)**
```powershell
python scripts/build_index.py `
  --input-dir ".\data\Public_Civil_Service_LLM_Data\Training\01.원천데이터\TS_국립아시아문화전당"
```

### 2.1. 주요 옵션
| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--input-dir` | `data/Civil_complaints_data` | 입력 원천데이터 디렉토리 |
| `--collection-name` | `civil_cases_v1` | ChromaDB 컬렉션명 |
| `--batch-size` | `20` | BE2 인덱싱 배치 크기 |
| `--limit` | `0` (전체) | 처리할 최대 JSON 파일 수 |
| `--rebuild` / `--no-rebuild` | `--rebuild` | 컬렉션 초기화 후 재빌드 / 기존 위에 upsert |

> ⚠️ 기본값(`--rebuild`)은 **첫 배치에서 해당 컬렉션을 초기화**한 뒤 재인덱싱합니다. 기존 데이터를 유지하려면 `--no-rebuild`를 붙이세요.

---

## 3. 인덱싱 결과 확인

### 3.1. Swagger UI에서 검색 테스트
브라우저에서 접속:
```
http://127.0.0.1:8000/docs
```
`/api/v1/search` 엔드포인트로 테스트 검색이 가능합니다.

추가로, ChromaDB 저장 내용을 FastAPI에서 바로 확인할 수 있는 read-only 디버그 엔드포인트가 있습니다.

- `GET /api/v1/chroma/collections`: 컬렉션 목록
- `GET /api/v1/chroma/collections/{collection_name}/count`: 컬렉션 count
- `GET /api/v1/chroma/collections/{collection_name}/sample?limit=5`: 샘플 문서/메타데이터

> ⚠️ `Error loading hnsw index`가 발생하는 환경에서도, `sample`은 sqlite 폴백으로 샘플을 반환하도록 구현되어 있습니다.

검색 요청 예시:
```json
{
  "request_id": "TEST-001",
  "query": "단체 관람 예매 방법",
  "top_k": 5,
  "filters": {
    "region": "광주",
    "category": "문화관광",
    "created_at": null,
    "date_from": "2024-01-01",
    "date_to": "2024-12-31",
    "entity_labels": []
  },
  "collection_name": "civil_cases_v1"
}
```

> ⚠️ 필터 미사용 시에도 `created_at`은 빈 문자열이 아닌 **`null`**로 보내야 합니다 (ISO-8601 검증 오류 방지).

### 3.2. ChromaDB 직접 덤프
저장된 모든 청크의 본문/메타데이터를 파일로 출력합니다.

```powershell
python -c "
import json, chromadb
client = chromadb.PersistentClient(path='data/chroma_db')
collection = client.get_collection('civil_cases_v1')
result = collection.get(limit=collection.count())
with open('chromadb_dump.txt', 'w', encoding='utf-8') as f:
    f.write(f'총 청크 수: {len(result[\"ids\"])}\n')
    for i in range(len(result['ids'])):
        f.write(f'\n========== [{i+1}] ==========\n')
        f.write(f'ID: {result[\"ids\"][i]}\n')
        f.write(f'내용:\n{result[\"documents\"][i]}\n')
        f.write(f'메타:\n{json.dumps(result[\"metadatas\"][i], ensure_ascii=False, indent=2)}\n')
print('done')
"
```
→ `chromadb_dump.txt` 파일이 UTF-8로 저장됩니다.

> ⚠️ PowerShell의 `>` 리다이렉션은 UTF-8 출력을 깨뜨리므로, Python 내부에서 파일에 직접 쓰는 위 방식을 사용하세요.

### 3.3. (권장) 스크립트로 샘플/덤프 보기
출력이 너무 길어지지 않게, 샘플/덤프를 위한 스크립트를 제공합니다.

**컬렉션 목록**
```powershell
python scripts/inspect_chromadb.py list
```

**건수 확인**
```powershell
python scripts/inspect_chromadb.py count --collection civil_cases_v1
```

**샘플 5개(JSON) 출력**
```powershell
python scripts/inspect_chromadb.py sample --collection civil_cases_v1 --limit 5
```

**전체 덤프(JSONL, 문서+메타데이터)**
```powershell
python scripts/inspect_chromadb.py dump --collection civil_cases_v1 --output logs/chroma/civil_cases_v1.jsonl
```

**(폴백) HNSW 인덱스 로딩 오류가 나는 경우에도 sqlite로 내용 확인**
```powershell
python scripts/inspect_chromadb.py sqlite --action docs --collection civil_cases_v1 --limit 5
```

**(폴백) 컬렉션 전체를 JSONL로 덤프**
```powershell
python scripts/inspect_chromadb.py sqlite --action dump --collection civil_cases_v1 --output logs/chroma/civil_cases_v1.sqlite_dump.jsonl --limit 0
```

---

## 4. 자주 발생하는 에러

| 에러 메시지 | 원인 | 해결 |
|------------|------|------|
| `Torch not compiled with CUDA enabled` | CPU 전용 PyTorch가 설치되어 있음 | CUDA PyTorch 재설치 또는 `$env:EMBEDDING_DEVICE="cpu"` 후 **FastAPI 재시작** |
| `chromadb.errors.InternalError: Error loading hnsw index` | HNSW 인덱스 파일 손상/누락(혹은 버전 불일치 등) | (1) 데이터 확인은 `inspect_chromadb.py sqlite` 폴백 사용 (2) 검색 정상화는 HNSW 재생성이 가장 확실: `python scripts/repair_chromadb_hnsw.py --device cpu --target-persist-dir data/chroma_db_rebuilt` 실행 후 앱에서 `CHROMA_DB_PATH`를 새 경로로 전환 |
| `model not found: exaone3.5:7.8b` | Ollama 모델 미설치 | `ollama pull exaone3.5:7.8b` |
| `Connection refused (127.0.0.1:8000)` | FastAPI 서버 미기동 | Step 1 먼저 실행 |
| `Connection refused (11434)` | Ollama 서버 미기동 | `ollama serve` 또는 Ollama Desktop 실행 |
| `날짜 필터는 ISO-8601 형식이어야 합니다` | `created_at`을 빈 문자열로 전송 | `null` 또는 `"2024-01-01T00:00:00+09:00"` 형식 사용 |

---

## 5. 데이터 규모와 처리 시간

원천데이터 파일 수:
- 국립아시아문화전당: 약 841개
- 중앙행정기관 / 지방행정기관: 그 외

| 범위 | 파일 수 | 예상 시간 (GPU) |
|------|---------|----------------|
| `--limit 50` (검증용) | 50개 | 5~10분 |
| 국립아시아문화전당 단일 기관 | 약 841개 | 1~2시간 |

> ⚠️ **반드시 `01.원천데이터` 하위 경로를 지정하세요.** 상위 `Training/` 경로를 그대로 넣으면 라벨링데이터(약 11만 개)까지 포함되어 인덱싱이 사실상 끝나지 않습니다.

먼저 `--limit 50`으로 검증한 뒤 점진적으로 확대하시길 권장합니다.

---

## 6. 저장 데이터 형식 (참고)

ChromaDB에 저장되는 한 chunk의 구조:

| 항목 | 설명 |
|------|------|
| `id` | `{case_id}::{case_id}__chunk-{N}` |
| `document` | 임베딩 대상 본문 (관찰/결과/요청/배경 결합, "없음" 등 무의미 텍스트는 제외) |
| `embedding` | `BAAI/bge-m3` 임베딩 벡터 |
| `metadata.case_id` | 민원 고유 ID |
| `metadata.region` / `category` | 검색 필터 (예: `광주`, `문화관광`) |
| `metadata.created_at` / `created_at_ts` | ISO 일시 / Unix timestamp (날짜 범위 필터) |
| `metadata.entity_labels` | `TIME\|ADMIN_UNIT\|FACILITY` (파이프 구분) |
| `metadata.structuring_confidence` | LLM 구조화 신뢰도 (0~1) |
| `metadata.title` / `summary_*` | UI 표시용 요약 |

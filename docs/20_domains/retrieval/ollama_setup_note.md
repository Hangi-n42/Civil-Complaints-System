# Ollama 로컬 연동 확인 메모 (Week 1, BE2)

문서 버전: v1.0  
작성일: 2026-03-17  
담당: BE2 (민건)

## 1. 목적

로컬 환경에서 Ollama + `qwen2.5:7b-instruct` 호출 가능 여부를 확인한다.

## 2. 점검 명령

```bash
# Ollama 설치 확인
ollama --version

# 모델 확인
ollama list

# 단건 생성 테스트
curl http://localhost:11434/api/generate \
  -d '{
    "model": "qwen2.5:7b-instruct",
    "prompt": "다음 문장을 한 줄로 요약해줘: 야간 가로등 고장 민원이 반복 발생한다.",
    "stream": false
  }'
```

## 3. 체크리스트

- [x] Ollama 실행 중 (`http://localhost:11434` 응답 가능)
- [x] 모델 목록에 `qwen2.5:7b-instruct` 존재
- [x] JSON 응답 수신 성공 (`response` 필드 확인)
- [x] 평균 응답시간 기록 (cold start / warm start)

## 3-1. 실제 점검 결과 (2026-03-17)

- 설치: `winget install -e --id Ollama.Ollama`
- 버전 확인: `ollama version is 0.18.0`
- 모델 확인: `qwen2.5:7b-instruct` (4.7GB)
- 단건 실행: `ollama run qwen2.5:7b-instruct` 정상 응답
- HTTP 연동: `POST http://localhost:11434/api/generate` 정상 응답

추가 확인:
- 앱 내부 경로(`app/generation/service.py`)에서 `call_ollama` 호출 성공
- `/api/v1/qa` 호출은 로컬 CPU 환경에서 응답시간이 길고 JSON 파싱 불안정 케이스가 간헐 발생
- 현재 `/api/v1/qa`는 파싱 실패 시 폴백 응답 + validation warning을 반환하도록 처리됨

판정:
- **설치/실행/연동 가능**
- **Week 1 기준으로 PoC 착수 가능** (성능/파싱 안정화는 Week 2 튜닝 과제로 이관)

## 4. 실패 시 우선 대응

1. `ollama serve` 실행 여부 확인
2. 모델 누락 시 `ollama pull qwen2.5:7b-instruct`
3. 포트 충돌 시 `OLLAMA_BASE_URL` 환경변수 재설정
4. timeout 발생 시 프롬프트 길이 축소

## 5. 리스크 및 폴백

### 리스크: 로컬 자원 부족으로 지연 증가
- 징후: 단건 생성에도 응답이 5초 이상 지연
- 원인: 모델 로딩 비용, 메모리 부족
- 예방책: 워밍업 요청 1회 수행, 동시요청 제한
- 대응책: max_tokens/컨텍스트 길이 축소
- 최악의 경우 폴백안: 더 작은 모델로 임시 전환

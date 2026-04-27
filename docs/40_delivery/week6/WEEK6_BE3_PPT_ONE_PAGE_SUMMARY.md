# BE3 벤치마크 한 페이지 요약

작성일: 2026-04-26

## 1. 모델 선정 과정

- Week4에서는 `exaone3.5:7.8b-instruct`가 기본 운영 후보였다. 답변 안정성과 지연이 가장 균형적이었다.
- `ax4-light-local:latest`는 답변은 약했지만 가장 빨라서 데모/고속 경로 후보로 남겼다.
- `gemma3:12b`는 균형형, `gemma4:26b`와 `gemma4:e4b`는 실험군으로 봤다.
- Week5 새 추출 로직 적용 후에는 `ax4-light-local:latest`가 strict answer 1.0과 최저 지연을 동시에 보여 시연 후보로 더 유리해졌다.

## 2. 모델 선정 이유

- **ax4-light-local:latest**: 가장 빠르고, 새 로직 후 답변 안정성도 확보.
- **exaone3.5:7.8b-instruct**: 품질과 안정성의 균형이 좋아 백업 기본 모델로 적합.
- **gemma3:12b**: 품질은 충분하지만 속도 메리트가 작아 보조 후보.
- **gemma4:26b / gemma4:e4b**: 운영 기본보다 비교·실험용 성격이 강함.

## 3. 벤치마크 주요 로직 변경점

- strict / repaired 지표를 분리해 모델 원본 성능과 파이프라인 보정 성능을 구분했다.
- answer 복구 로직을 추가해 `answer`가 비어도 대체 필드, raw 재추출, context snippet 순서로 복원한다.
- citation이 비거나 불완전하면 repair/fallback으로 보정한다.
- integrity gate와 compact 재시도로 빈 답변·citation 불일치 케이스를 한 번 더 복구한다.
- 결과 출력은 raw responses / parsed answers / summary md / json으로 분리해 추적 가능하게 했다.

## 4. 기본 세팅 값

| 항목 | 값 | 의미 |
|---|---:|---|
| temperature | 0.2 | 응답 랜덤성 |
| num_ctx | 1024 | 컨텍스트 길이 |
| num_predict | 128 | 최대 생성 토큰 수 |
| timeout_sec | 90 | 응답 대기 시간 |
| repetitions_per_case | 1 | 케이스당 반복 횟수 |

## 5. 핵심 결과 한 줄

- Week4 기준: `exaone3.5:7.8b-instruct`가 가장 안정적, `ax4-light-local:latest`는 속도 우선.
- Week5 sample50 기준: 새 answer 복구 로직으로 `ax4-light-local:latest`가 strict answer 1.0과 최저 지연을 확보.

## 6. 발표용 메시지

- "모델 자체를 바꾼 게 아니라, 답변을 복구하는 기준을 정교하게 만든 뒤 ax4가 가장 빠르고 안정적인 시연 후보임을 확인했다."

## 7. 성능 비교

| 모델 | strict | avg_latency_sec | 의미 |
|---|---:|---:|---|
| ax4-light-local:latest | 1.0 | 13.2170 | 가장 빠른 시연 후보 |
| exaone3.5:7.8b-instruct | 1.0 | 16.0846 | 안정적인 백업 기본 모델 |
| gemma4:26b | 1.0 | 18.3473 | 중간 속도 실험군 |
| gemma3:12b | 1.0 | 19.3726 | 가장 느린 편 |

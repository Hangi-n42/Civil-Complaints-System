# BE3 매뉴얼(현석)

문서 버전: v1.1  
기준 문서: [PRD](../00_overview/prd.md), [WBS](../00_overview/wbs_8weeks_v2_updated.md), [Week3 공통 인터페이스](../10_contracts/interfaces/week3/week3_common_interface.md), [Week3 BE3 인터페이스](../10_contracts/interfaces/week3/week3_be3_interface.md)  
작성일: 2026-03-11  
최신화: 2026-03-27 (M1 완료, M2 진행중 기준 반영)

## 1. 문서 목적

이 문서는 BE3의 안정성 책임을 API/생성/검증 관점에서 실행 항목으로 고정한다.  
핵심은 Week3~Week4에 검색-생성 연결 구간의 실패율을 낮추고, Week4 baseline 평가가 가능한 품질 게이트를 만드는 것이다.

## 2. BE3 한 줄 정의

**BE3는 API와 생성 결과의 정합성을 보장하고, JSON 파싱·citation·성능 안정화를 통해 데모 실패 확률을 줄이는 품질 오너다.**

## 3. 현재 단계 진단 (2026-03-27)

- M1(W1~W2): 완료
	- 에러 응답 래퍼/파싱 재시도 기초 규칙 정리
- M2(W3~W4): 진행중
	- 우선순위: `/index`, `/search` 안정화 + 모델 후보 3종 벤치마크 + 통합 리포트 품질 관리
	- Week4 진입 게이트: `/qa` JSON 안정화와 citation 정합성 검증 가능 상태

## 4. BE3 최종 책임 범위

### 주 책임
- API 에러 처리/응답 일관성 보장
- 생성 JSON 파싱 및 재시도 로직 안정화
- citation 정합성 검증 및 하이라이팅 포맷 유지
- 성능 로깅(지연/실패/메모리) 운영
- 후보 모델 2/3/4 벤치마크 실행 및 통합 리포트 반영

### 협업 책임
- BE1의 구조화 품질 이슈를 검증 규칙으로 연결
- BE2 retrieval 출력을 generation 입력 계약으로 고정
- FE에 validation/error/citation 표시용 필드 제공

### 담당 제외
- 검색 파라미터 최적화 주도(소유: BE2)
- 구조화 규칙 설계 주도(소유: BE1)
- UI 인터랙션 구현 주도(소유: FE)

## 5. 핵심 산출물 (현재~종료)

### 코드/모듈
- API 라우터: `app/api/routers/`
- 생성 서비스: `app/generation/service.py`
- 파서/검증 모듈: `app/generation/parsing/`, `app/generation/validators/`
- 에러 유틸: `app/api/error_utils.py`

### 리포트/로그
- 모델별 벤치마크 결과: `logs/evaluation/week3/model_benchmark_*.json`
- 통합 비교 리포트: `logs/evaluation/week3/model_benchmark_report_final.json`
- 성능/장애 로그: `logs/api/`, `logs/pipeline/`

### 운영 문서
- 파싱 실패 유형 및 재시도 규칙 문서
- OOM 대응 우선순위(컨텍스트 축소 -> 배치 축소 -> 모델 다운스케일)

## 6. 마일스톤별 실행 계획

## M2 (W3~W4, 현재 진행중)

### 목표
- 검색 API 안정화 + 생성 준비 품질 고정

### BE3 실행 항목
- [ ] `/index`, `/search` 오류 코드와 래퍼 응답 정합성 점검
- [ ] 요청 단위 지연시간/실패 로그 필드 표준화
- [ ] 후보 모델 2/3/4 벤치마크 실행
- [ ] 통합 리포트에 모델별 실패 원인 분류 반영
- [ ] Week4 `/qa` JSON 파싱 재시도 전략 사전 점검

### 완료 기준
- [ ] API 에러 포맷 불일치 이슈 0건
- [ ] 후보 3개 모델 결과가 통합 리포트에 반영됨
- [ ] parsing 실패 재현 케이스와 대응 규칙이 정리됨

## M3 (W5~W6)

### 목표
- Adaptive RAG 구간에서 파싱/인용 정합성 유지

### BE3 실행 항목
- topic/length/multi 분기별 파싱 성공률 비교
- citation 매핑 검증 강화(chunk_id, case_id, snippet)
- `normalize_response()` 기준 고정

### 완료 기준
- 분기 적용 후에도 JSON 파싱 성공률이 안정적으로 유지
- citation 정합성 저하 구간에 대한 보정안 확보

## M4 (W7~W8)

### 목표
- 데모 안정성 최종 고정

### BE3 실행 항목
- 4-bit/8-bit 조건 비교 최종 정리
- OOM 폴백 경로 통합 테스트
- 장애 메시지/복구 시나리오 문서화

### 완료 기준
- 2시간 데모 중 치명 장애 회피 가능한 운영 절차 확보
- 성능/안정성 결과가 발표 근거로 연결됨

## 7. 입출력 계약 (핸드오프 명세)

### BE3가 받아야 할 것
- BE1: 구조화 필드 규칙, 오류 사례, 평가셋 고정 버전
- BE2: SearchResult, retrieval trace, 메타필드 정의
- FE: validation/citation/error 노출 요구사항

### BE3가 넘겨줘야 할 것
- 표준 에러 코드/메시지/재시도 가능 여부
- citation/하이라이트 출력 포맷
- JSON 파싱 실패 분류 및 재시도 정책
- 모델/성능/안정성 리포트

## 8. 주간 운영 체크리스트

- [ ] 파싱 실패 케이스를 유형별로 분류했는가?
- [ ] citation이 실제 검색 청크와 일치하는가?
- [ ] API 지연시간 평균/95p를 주간 기록했는가?
- [ ] OOM/timeout 발생 시 fallback이 즉시 동작하는가?
- [ ] FE 표시 필드와 백엔드 응답 포맷이 일치하는가?

## 9. BE3 핵심 리스크 관리

### 리스크 1: JSON 파싱 실패 누적
- 징후: `/qa` 응답의 파싱 에러가 반복
- 원인: 모델 출력 형식 불안정, 템플릿 일탈
- 예방책: JSON 강제 프롬프트 + 낮은 temperature 유지
- 대응책: 재시도 로직과 compact prompt fallback 적용
- 최악의 경우 폴백안: 파싱 안정 모델을 baseline으로 고정

### 리스크 2: citation 정합성 저하
- 징후: 답변은 자연스럽지만 인용 근거가 불일치
- 원인: retrieval trace 누락/매핑 로직 오류
- 예방책: chunk_id/case_id/snippet 삼중 검증
- 대응책: 불일치 케이스 자동 검출 후 재매핑
- 최악의 경우 폴백안: 검증 통과 citation만 UI 노출

### 리스크 3: 성능 병목 후반 발견
- 징후: 데모 직전 timeout/OOM 급증
- 원인: 로깅 부재, 사전 부하 테스트 부족
- 예방책: M3부터 주간 지연/메모리 추적
- 대응책: 컨텍스트/배치 축소, 모델 다운스케일
- 최악의 경우 폴백안: 경량 모델 + 축소 시나리오로 데모 운영

## 10. 최종 완료 기준

- API와 생성 응답이 계약 포맷으로 안정 반환된다.
- JSON 파싱/재시도 및 citation 검증이 자동화되어 있다.
- 성능 병목과 OOM 대응 절차가 문서화되어 있다.
- 안정성 측면에서 데모 실패 가능성을 실질적으로 낮췄다.

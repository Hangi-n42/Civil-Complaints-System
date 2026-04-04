# Harness 기반 프롬프트 에이전트 중심 설계

문서 버전: v3.3
작성일: 2026-04-05
기준 문서: docs/00_overview/hanes.md, docs/00_overview/prd.md, docs/00_overview/wbs_8weeks_v2_updated.md, docs/00_overview/harness_feedback.md

## 0. 문서 목적

이 문서는 런타임 제어 중심 하네스를 프롬프트 에이전트 중심으로 재구성하고, 프롬프트 미들웨어 전제에서 실제 운영 가능한 상태/검증/에스컬레이션 계약을 정의한다.

핵심 목표:
- 작업 판단과 분기의 1차 책임을 프롬프트 에이전트로 이동
- 오케스트레이터(main_instruction)가 미들웨어 역할을 수행하도록 명시
- 상태 일관성은 이중 상태 컨텍스트 패턴으로 보장
- 비수렴 루프, 상태 limbo, 과도 차단을 줄이는 운영 계약 수립

## 1. 설계 원칙

프롬프트 중심 전환 원칙:
- Agent First: 실행 경로는 에이전트 계획을 우선한다.
- Prompt Middleware: 미들웨어는 별도 코드가 아니라 오케스트레이터의 검증/판정 행위로 구현한다.
- Explainability First: 핵심 판단은 rationale 계열 필드로 근거를 남긴다.
- Progressive Control: 저위험은 유연하게, 고위험은 엄격하게 운영한다.
- Human Override Ready: Human Gate 트리거와 상태 전이를 문서화한다.

Human Gate 유형:
- REVIEW_REQUIRED
- MANDATORY_APPROVAL
- MANUAL_OVERRIDE

## 2. 목표 아키텍처

구성 요소:
1. main_instruction: 오케스트레이션 + 프롬프트 미들웨어(검증/판정/로그)
2. part_agent: 요구 해석, 타겟 후보 수집, 변경 초안 생성
3. work_agent: 실제 변경/검증/증빙 작성

프로젝트 매핑:
- .github/copilot-instructions.md (워크스페이스 기본 지시 엔트리)
- .github/agents/main_instruction.prompt.md
- .github/agents/part_agent.prompt.md
- .github/agents/work_agent.prompt.md

기본 적용 규칙:
- 워크스페이스 기본 지시 파일은 .github/copilot-instructions.md를 사용한다.
- .github/copilot-instructions.md는 기본 오케스트레이터 프롬프트를 .github/agents/main_instruction.prompt.md로 고정한다.
- task 분해 단계는 .github/agents/part_agent.prompt.md, 실행 단계는 .github/agents/work_agent.prompt.md를 참조한다.
- 규칙 충돌 시 우선순위는 다음과 같다.
  1. .github/copilot-instructions.md
  2. .github/agents/main_instruction.prompt.md
  3. .github/agents/part_agent.prompt.md, .github/agents/work_agent.prompt.md

## 3. 상태 소유 모델 재정의

### 3.1 소유권 모델

- 1차 소유권: 프롬프트 에이전트(의사결정/계획/근거)
- 2차 소유권: 오케스트레이터(main_instruction)의 정합성 검증/확정

운영 원칙:
- 상태는 제안(proposal)과 확정(commit)을 분리한다.
- 코드 미들웨어 없이 컨텍스트 내 이중 상태로 관리한다.
- 롤백은 proposal 폐기 + last_committed_state 유지로 정의한다.
- last_committed_state Lazy 주입 원칙:
  - 정상 흐름에서는 task_id와 committed_at만 last_committed_ref로 참조한다.
  - 아래 조건에서만 last_committed_state 전체를 재주입한다.
    - proposal이 REJECTED_STANDARD 또는 REJECTED_CRITICAL인 경우
    - Human Gate 진입 직전
    - 오케스트레이터가 INCONSISTENT 판정 시
  - 위 3개 조건을 Lazy 주입 예외 조건이라 부른다.

### 3.2 상태 업데이트 계약 (이중 상태 컨텍스트)

패턴 A - 정상 흐름(Lazy 주입 예외 미해당):

```json
{
  "last_committed_ref": {
    "task_id": "TASK-001",
    "committed_at": "ISO8601"
  },
  "proposal_under_review": {
    "state_update": {
      "assigned_to": "work_agent",
      "status": "IN_PROGRESS",
      "task_harness_mode": "EXPLORE",
      "mode_assignment_rationale": "single-file change, low failure cost",
      "evidence_tier": 1,
      "escalation_recommendation": false
    },
    "proposed_at": "ISO8601",
    "validation_status": "PENDING"
  }
}
```

패턴 B - 예외 흐름(Lazy 주입 예외 해당):

```json
{
  "last_committed_state": {
    "task_id": "TASK-001",
    "state_update": {
      "assigned_to": "work_agent",
      "status": "IN_PROGRESS",
      "task_harness_mode": "EXPLORE",
      "mode_assignment_rationale": "single-file change, low failure cost",
      "evidence_tier": 1,
      "escalation_recommendation": false
    },
    "committed_at": "ISO8601"
  },
  "proposal_under_review": {
    "state_update": {
      "assigned_to": "work_agent",
      "status": "IN_PROGRESS",
      "task_harness_mode": "BUILD",
      "mode_assignment_rationale": "interface contract affected",
      "evidence_tier": 2,
      "escalation_recommendation": false
    },
    "proposed_at": "ISO8601",
    "validation_status": "REJECTED_STANDARD",
    "rejection_reason": "retry_count_decreased"
  }
}
```

mode_retention_reason 필드 규칙:
- STEP 2를 통해 EXPLORE를 유지한 경우에만 포함한다.
- fast-path(STEP 1) 통과 시에는 생략한다(mode_assignment_rationale로 대체).

#### 전략 ①+② 동시 적용 결합 스키마

정상 흐름(예외 미해당 + 위반 없음):

```json
{
  "last_committed_ref": {
    "task_id": "TASK-001",
    "committed_at": "ISO8601"
  },
  "proposal_under_review": {
    "state_update": {
      "assigned_to": "work_agent",
      "status": "IN_PROGRESS"
    },
    "proposed_at": "ISO8601",
    "validation_status": "ACCEPTED"
  },
  "assertions": "PASSED"
}
```

예외 흐름(REJECTED_STANDARD + HARD_STANDARD 위반):

```json
{
  "last_committed_state": {
    "task_id": "TASK-001",
    "state_update": {
      "assigned_to": "work_agent",
      "status": "IN_PROGRESS",
      "task_harness_mode": "EXPLORE"
    },
    "committed_at": "ISO8601"
  },
  "proposal_under_review": {
    "state_update": {
      "assigned_to": "work_agent",
      "status": "IN_PROGRESS",
      "task_harness_mode": "BUILD"
    },
    "proposed_at": "ISO8601",
    "validation_status": "REJECTED_STANDARD",
    "rejection_reason": "retry_count_decreased"
  },
  "assertions": {
    "hard_standard": {
      "retry_count_should_not_decrease": false
    }
  }
}
```

예외 흐름(SOFT 위반, 수용 + 경고):

```json
{
  "last_committed_ref": {
    "task_id": "TASK-001",
    "committed_at": "ISO8601"
  },
  "proposal_under_review": {
    "state_update": {
      "assigned_to": "work_agent",
      "status": "IN_PROGRESS"
    },
    "proposed_at": "ISO8601",
    "validation_status": "ACCEPTED_WITH_WARN"
  },
  "assertions": {
    "soft": {
      "source_of_truth_refs_should_not_shrink": false
    }
  }
}
```

### 3.3 assertion 등급 정책

등급:
- HARD_CRITICAL: 상태 무결성 파괴 수준
- HARD_STANDARD: 전이/운영 규칙 위반
- SOFT: 품질 저하 가능성

오케스트레이터 행동:
- HARD_CRITICAL 위반: proposal 거부 + last_committed_state 전체 재주입(Lazy 주입 예외 ①) + MANDATORY_APPROVAL 진입
- HARD_STANDARD 위반: proposal 거부 + last_committed_state 전체 재주입(Lazy 주입 예외 ①) + 재호출 허용
- SOFT 위반: ACCEPTED_WITH_WARN + WARN 로그 + 리뷰 큐 적재
- 위반 없음: "assertions": "PASSED" 한 단어만 출력(full 블록 생략)

용어 정의:
- last_committed_ref: 정상 흐름에서 task_id + committed_at만 참조하는 경량 필드
- last_committed_state: Lazy 주입 예외 조건에서만 재주입하는 full 상태 블록

assertion 출력 규칙:
- 전체 3등급 블록은 위반 발생 시에만 출력한다.
- 위반이 없을 때는 반드시 "assertions": "PASSED"를 사용한다.
- HARD_CRITICAL 위반: hard_critical 블록만 출력 가능
- HARD_STANDARD 위반: hard_standard 블록만 출력 가능
- SOFT 위반: soft 블록만 출력 + WARN 로그

Assertion 실패 이벤트 로그 예시(텍스트 단일 행):

```text
[REJECT:STD] TASK-001 | retry_count_decreased | action:PROPOSAL_REJECTED
```

### 3.4 soft assertion 처리 정책

기본 정책:
- SOFT 위반은 차단하지 않고 ACCEPTED_WITH_WARN 처리
- 오케스트레이터가 WARN 이벤트 로그를 append-only로 출력

누적 격상 정책:

```json
{
  "soft_assertion_escalation_policy": {
    "enabled": true,
    "threshold": 3,
    "escalate_to": "HARD_STANDARD",
    "reset_on_task_complete": true
  }
}
```

WARN 이벤트 로그 예시:

```text
[WARN:SOFT] TASK-001 | source_of_truth_refs_shrink | count:1/3
```

### 3.5 이벤트 로그 포맷 (텍스트 단일화)

모든 이벤트 로그는 단일 행 포맷을 사용한다.

포맷:
[{등급}:{유형}] {task_id} | {assertion_key 또는 사유} | action:{action}

등급 약어:
- CRIT: HARD_CRITICAL
- STD: HARD_STANDARD
- WARN: SOFT
- GATE: Human Gate 진입
- DEAD: 교착 감지
- TOUT: TIMEOUT
- INCON: INCONSISTENT

예시:
- [REJECT:STD] TASK-001 | retry_count_decreased | action:PROPOSAL_REJECTED
- [REJECT:CRIT] TASK-001 | state_regressed | action:MANDATORY_APPROVAL_GATE
- [WARN:SOFT] TASK-001 | source_of_truth_refs_shrink | count:1/3
- [GATE:MANDATORY] TASK-001 | trigger:HARD_CRITICAL_violated
- [GATE:REVIEW] TASK-001 | trigger:escalation_recommendation=true
- [DEAD:STEP2] TASK-001 | part_agent_recall | candidates_failed:3
- [TOUT:RUN] TASK-001 | turns_exceeded:3 | retry:1/2
- [INCON:FIELD] TASK-001 | task_id_mismatch | action:MANDATORY_APPROVAL_GATE
- [SOFT_ESCALATE] TASK-001 | source_of_truth_refs_shrink | count:3/3->HARD_STANDARD

규칙:
- 복수 이벤트는 줄 단위로 나열한다.
- 타임스탬프는 기본 생략한다(필요 시 선택 추가).
- 이벤트 없는 턴에는 이벤트 로그 항목을 생략한다.

텍스트화 제외(계속 JSON 유지):
- soft_assertion_escalation_policy 등 정책 정의 JSON
- 이유: 설계 시점 설정값으로 구조적 파싱이 필요함
```

## 4. 프롬프트 주도 의사결정 프레임

### 4.1 mode assignment checklist

평가는 빠른 경로(fast-path)를 먼저 확인하고, 통과 시 전체 평가를 생략한다.

STEP 1 - fast-path 선제 확인(3개 항목):
- demo_impact == false
- interface_contract_impact == false
- target_file_count <= 2

판정:
- 3개 모두 충족: EXPLORE fast-path 확정
- mode_assignment_rationale: "EXPLORE (fast-path: safe envelope satisfied)"
- 나머지 4개 항목 평가는 생략

STEP 2 - 전체 checklist 평가(STEP 1 미통과 시에만):
- artifact_required: yes/no
- context_transfer_cost_expected: low/medium/high
- failure_cost: low/medium/high
- estimated_execution_scope: narrow/broad

필드명 통일:
- fast-path와 safe envelope 모두 target_file_count를 사용한다.
- estimated_file_count는 사용하지 않는다.

### 4.2 모드 배정 규칙

기본 규칙:
- EXPLORE 기본 진입, 필요 시 BUILD 승격
- mode_assignment_rationale 필수 기록
- Section 4.1 STEP 1(fast-path) 통과 시 승격 점수표 평가는 생략하고 EXPLORE로 확정한다.
- 승격 점수표는 STEP 2 진입 시에만 적용한다.

주의(잠정값):
아래 점수는 운영 데이터 수집 전 잠정값이며, 누적 데이터 100건 이상 시 교정한다.

승격 점수표(잠정):
- 다중 파일 수정(2개 이상): +2
- 인터페이스/계약 영향 가능성: +3
- context_transfer_cost high 예상: +2
- evidence_tier 2 이상 필요: +2
- 반복 실패/비수렴 루프 이력: +1

판정:
- 총점 4 이상: BUILD 검토
- demo_impact=true: BUILD 우선 검토

### 4.3 safe envelope

아래 조건을 모두 만족하면 EXPLORE 유지를 우선한다.
- requires_file_write == false 또는 target_file_count <= 2
- demo_impact == false
- interface_contract_impact == false
- artifact_required == false
- context_transfer_cost_expected != high
- estimated_execution_scope == narrow

감점 규칙(조건 만족 수 기준):
- 0~2개 만족: -0
- 3~4개 만족: -1
- 5~6개 만족: -2

## 5. 에이전트별 운영 계약

### 5.1 main_instruction

책임:
- 요청 분류
- 우선순위 결정
- 작업 분해
- 모드/티어 배정
- 담당자 전환
- Human Gate 판단 및 review_context 출력
- assertion 평가 및 proposal 확정/거부

출력 순서:

[필수 항목 - 매 턴 포함]
1. 요청 분류
2. 현재 우선순위
3. 작업 목록
4. 재조정 규칙
5. task_harness_mode 배정
6. mode_assignment_rationale
7. evidence_tier 배정
8. state_update 또는 proposal_under_review(last_committed_ref 포함)

[조건부 항목 - 조건 충족 시 포함]
9. assertion 평가 결과
  - 위반 없음: "assertions": "PASSED"
  - 위반 발생: 해당 등급 블록만 출력
10. 이벤트 로그
  - 이벤트 발생 시에만 단일 행 텍스트 포맷으로 출력
  - 이벤트 없는 턴에는 항목 자체를 생략

### 5.2 part_agent

책임:
- 요구 해석 및 핵심 제약 추출
- target 후보 제시
- 파일별 변경 가설 정리

입력 확장:
- recall_context(교착 해소 단계에서 필수)

출력:
- task_breakdown
- target_candidates
- decision_rationale
- state_update
- assertions (조건부: 위반 없으면 "PASSED", 위반 시 해당 등급 블록)

### 5.3 work_agent

책임:
- 후보 파일 검증
- 변경 실행
- 테스트/증빙 조립
- 실패 시 원인 분류와 재시도 전략 제안

출력:
- execution_plan 또는 execution_report
- evidence_links
- artifact_verification
- rejection_recovery(전체 후보 기각 시 필수)
- state_update
- assertions (조건부: 위반 없으면 "PASSED", 위반 시 해당 등급 블록)

rejection_recovery 예시:

```json
{
  "rejection_recovery": {
    "rejection_rationale": "A: 의존성 누락, B: 스키마 불일치, C: 실행 범위 초과",
    "alternative_hypothesis": "D 파일 경로로 접근 시 범위 내 처리 가능",
    "self_retry_count": 1,
    "max_self_retry": 1
  }
}
```

### 5.4 에이전트 간 분쟁 해소 계약

교착 조건:
- part_agent의 target_candidates를 work_agent가 전부 기각

3단계 해소 프로토콜:
1. work_agent 자체 재시도(최대 1회)
2. 실패 시 part_agent 재호출(recall_context 주입)
3. 재호출 실패 시 오케스트레이터 중재 + Human Gate(MANDATORY_APPROVAL)

recall_context 예시:

```json
{
  "recall_context": {
    "trigger": "work_agent_self_retry_failed",
    "failed_candidates": ["A", "B", "C"],
    "rejection_rationale": "...",
    "max_recall": 1
  }
}
```

deadlock_resolution 예시:

```json
{
  "deadlock_resolution": {
    "trigger": "part_agent_recall_failed",
    "escalation_recommendation": true,
    "escalation_reason": "중재 불가 사유",
    "human_gate": "MANDATORY_APPROVAL"
  }
}
```

### 5.5 Human Override 운영 계약

Human Gate 트리거:
- escalation_recommendation=true
- HARD_CRITICAL assertion 실패
- 교착 3단계 진입
- demo_impact=true + BUILD
- 운영자 수동 트리거

Gate 동작:
- REVIEW_REQUIRED: WAITING_FOR_HUMAN 전이, review_context 출력, 응답 대기
- MANDATORY_APPROVAL: 승인 전 에이전트 호출 중단
- MANUAL_OVERRIDE: override_instruction 수동 반영

Human 리뷰 결과 계약:

```json
{
  "human_review_result": {
    "task_id": "TASK-001",
    "gate_type": "REVIEW_REQUIRED",
    "reviewer": "operator_id",
    "decision": "APPROVE | REJECT | MODIFY",
    "override_instruction": "...(MODIFY 시 필수)",
    "review_reason": "...",
    "logged_at": "ISO8601"
  }
}
```

상태 전이:
- IN_PROGRESS -> WAITING_FOR_HUMAN
- WAITING_FOR_HUMAN -> IN_PROGRESS(approve/modify)
- WAITING_FOR_HUMAN -> BLOCKED(reject/무응답)

## 6. 프롬프트 미들웨어 역할 설계

필수 기능:
- contract validation
- transition validation
- assertion grade evaluation
- forbidden update filter
- append-only event logging
- proposal reject/accept 판정

상태 불일치 대응:
- task_id 불일치, 필수 필드 누락 등 정합성 실패 시 MANDATORY_APPROVAL 진입
- 자동 재시도 금지

```text
[INCON:FIELD] TASK-001 | task_id_mismatch | action:MANDATORY_APPROVAL_GATE
```

비필수 기능(옵션) 활성화 정책:
- 기본 상태는 모두 비활성
- 자동 활성화 금지, 운영자 수동 활성화만 허용
- 활성화 사유/예상 유지 턴/비활성화 조건 로그 필수

옵션 기능:
- 세부 모드 강제 로직
- 과도한 사전 차단형 체크
- 에이전트 reasoning 대체 판정

활성화 이벤트 로그 예시:

```text
[GATE:OPTION] TASK-001 | feature:세부 모드 강제 로직 | action:ACTIVATED
```

## 7. evidence tier 재정의

- Tier 1: 프롬프트 판단 로그 + 변경 요약
- Tier 2: 실행 명령 + 핵심 로그 + 수정 파일 경로
- Tier 3: Tier 2 + 결과 산출물 + PR/커밋 링크 + 게이트 통과 플래그

적용 기준:
- EXPLORE 기본 Tier 1
- BUILD 기본 Tier 2
- 외부 검증/배포 연계 시 Tier 3

## 8. 호출 정책

호출 type:
- CALL_SKILL
- CALL_SUB_AGENT
- CALL_FORK

call lifecycle (턴 기반):
- REQUESTED
- ACKED
- RUNNING
- SUCCEEDED
- FAILED
- TIMEOUT

timeout_policy 예시:

```json
{
  "timeout_policy": {
    "max_ack_turns": 1,
    "max_run_turns": 3,
    "on_timeout": {
      "status": "TIMEOUT",
      "mapped_to": "FAILED",
      "timeout_reason_required": true,
      "retry_eligible": true,
      "max_timeout_retry": 2
    }
  }
}
```

CALL_FORK 선언 계약:
- fork_mode: PARALLEL | SEQUENTIAL
- aggregation_policy: ALL_SUCCESS | ANY_SUCCESS | BEST_EFFORT
- failure_behavior: ABORT_ALL | CONTINUE | ESCALATE

CALL_FORK 예시:

```json
{
  "call_type": "CALL_FORK",
  "fork_mode": "PARALLEL",
  "aggregation_policy": "ALL_SUCCESS",
  "failure_behavior": "ABORT_ALL",
  "selection_reason": "독립적인 파일 검증 작업으로 병렬화 가능"
}
```

## 9. 전환 로드맵

1단계: 문서/프롬프트 동기화
- 모드 체크리스트, 이중 상태 계약, assertion 등급 계약 반영

2단계: 오케스트레이터 미들웨어 정착
- proposal/commit 흐름과 이벤트 로그 블록 표준화

3단계: 운영 데이터 수집
- mode_assignment_rationale, mode_retention_reason, escalation_reason 100건 이상 누적

4단계: 교정
- EXPLORE->BUILD 재배정 비율, BUILD 과대분류 비율 분석
- 임계값 조정은 운영자 수동 수행(자동 조정 금지)
- 점수표 버전 업데이트와 근거 로그 의무화

## 10. 리스크와 대응

리스크:
- 에이전트 자율성 증가로 판단 편차 확대
- 프롬프트 품질 저하 시 상태 일관성 저하
- 옵션 기능 장기 활성화로 미들웨어 크리프 발생

대응:
- assertion 등급 문서화(HARD_CRITICAL/HARD_STANDARD/SOFT)
- 프롬프트 템플릿 표준화 및 버전 관리
- 옵션 기능 활성화 시 expected_duration_turns와 deactivation_trigger 강제 기록

## 11. 완료 기준

- 프롬프트 에이전트가 모드/전이/증빙 결정을 주도한다.
- 오케스트레이터가 이중 상태 컨텍스트로 proposal/commit을 관리한다.
- 교착 해소 프로토콜(5.4)과 Human Gate 계약(5.5)이 운영에 적용된다.
- TIMEOUT 포함 호출 lifecycle과 CALL_FORK 의미론이 문서화된다.
- soft assertion 누적 격상 정책이 로그 기반으로 동작한다.

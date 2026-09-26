# 평가 Runbook

- 문서 상태: runbook
- 문서 버전: v2.0
- 범위·경로 정리일: 2026-09-26
- 명령 재실행: 미수행; 아래 다중행 명령은 PowerShell 문법
- 기준 코드:
  - `scripts/evaluate_complaint_intelligence_scenarios.py`
  - `scripts/evaluate_complaint_intelligence_holdout.py`
  - `scripts/evaluate_duplicate_merge_real_holdout.py`
  - `scripts/evaluate_duplicate_merge_labeled_pairs.py`
  - `scripts/evaluate_retrieval.py`
  - `scripts/evaluate_qa.py`
- 관련 문서:
  - `docs/20_domains/complaint_intelligence/README.md`
  - `docs/50_issues/complaint_intelligence_local_llm_operations.md`

## 평가 종류 구분

- 기존 민원 온라인 평가는 `app/evaluation/civil_llm_rubric.py`의 Qwen Q0~Q7 5그룹이며 Q2 재사용 재평가는 4회다.
- [오프라인 proxy](llm_rubric_civil_reply_evaluation.md)는 Q0~Q8, 0~10점 규칙 기반 평가로 별도 도구다.
- 아래 EXAONE 명령은 Complaint Intelligence 평가이며 온라인 답변 평가 모델 설정을 대체하지 않는다.
- 신규 지식 제품의 12개 과제는 입력만 고정됐으며 제품 비교 실행 결과는 없다.
- 먼저 [로컬 실행 안내](local_dev_runbook.md)에 따라 가상환경을 활성화한다. 아래 명령은 PowerShell 기준이며 macOS에서는 줄 연결을 셸 문법에 맞추거나 한 줄로 실행하고 경로 구분자를 `/`로 바꾼다.

## 기본 원칙

- curated scenario와 open-world holdout을 구분합니다.
- Fake provider 결과와 Local LLM 결과를 섞어 해석하지 않습니다.
- Local LLM은 `exaone3.5:7.8b` 기준으로 기록된 리포트가 많지만, 실행 환경에 따라 latency가 달라질 수 있습니다.
- PII leak과 forbidden AI-ops term은 별도 검사합니다.

## Complaint Intelligence curated 평가

```powershell
python scripts\evaluate_complaint_intelligence_scenarios.py --provider fake --output reports\complaint_intelligence_eval_report_final_fake.json
```

Local LLM:

```powershell
python scripts\evaluate_complaint_intelligence_scenarios.py `
  --provider local `
  --model exaone3.5:7.8b `
  --base-url http://localhost:11434 `
  --prompt-mode compact `
  --timeout-seconds 600 `
  --num-predict 1024 `
  --checkpoint-dir reports\complaint_intelligence_eval_checkpoints `
  --resume `
  --output reports\complaint_intelligence_eval_report_final_local.json
```

주의:

- smoke test를 전체 평가처럼 보고하지 않습니다.
- checkpoint 파일은 PR 포함 전 정리합니다.

## Complaint Intelligence holdout 평가

holdout 생성:

```powershell
python scripts\build_complaint_intelligence_holdout.py
```

holdout 평가:

```powershell
python scripts\evaluate_complaint_intelligence_holdout.py --provider fake --output reports\complaint_intelligence_holdout_eval_report.json
```

해석:

- holdout은 정답 라벨 기반 precision/recall 평가가 아닙니다.
- pipeline robustness와 qualitative readiness를 봅니다.

## Duplicate Merge 평가

```powershell
python scripts\evaluate_duplicate_merge_labeled_pairs.py
python scripts\evaluate_duplicate_merge_real_holdout.py
```

실제 사용 가능한 옵션은 스크립트 `--help`로 확인합니다.

## Retrieval/QA 평가

대표 스크립트:

- `scripts/evaluate_retrieval.py`
- `scripts/evaluate_qa.py`
- `scripts/eval_ndcg.py`
- `scripts/eval_bm25_morph.py`

retrieval v3 관련 결과는 주로 `reports/retrieval/v3/`에 있습니다.

## 문서/변경 검증

문서만 변경한 경우:

```powershell
git diff --check
```

코드나 스크립트 변경이 있는 경우 관련 pytest를 실행합니다.

```powershell
python -m pytest app\tests\unit -q
```

## PII leak check

최종 report와 seed에 전화번호/상세 주소가 없는지 확인합니다.

```powershell
rg "010-|[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}" data reports docs
```

## 자주 생기는 문제

- Local LLM timeout: checkpoint/resume으로 이어서 실행합니다.
- fallback rate 증가: raw response를 저장하기보다 failure reason과 verifier report를 먼저 봅니다.
- candidate 과다: 운영에서는 TTL/dedupe/candidate cap 정책을 검토합니다.
- demo DB와 real replay DB 혼용: source_name과 DB path를 분리합니다.

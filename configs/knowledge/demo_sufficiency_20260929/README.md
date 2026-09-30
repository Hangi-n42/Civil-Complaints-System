# 시연 데이터 충분성 실측

- `inventory.json`: 2026-09-29 확보 원본 CSV·XLSX·JSON의 행 수, 고유 ID, 연결 가능 여부 및 SHA-256 기록.
- 보행 링크는 통행 코드 첫 자리 `1`인 항목만 포함. 연결요소는 양 끝점이 모두 있는 링크의 무방향 ID 진단이며 실제 보행 경로나 영향값 계산이 아님.
- 원본은 기존 `data/knowledge` 경로에 유지. 새 대량 다운로드나 모델 호출 없음.
- 판정과 다음 작업: [데이터 충분성 검토](../../../docs/70_research/company_knowledge/demo_dataset_sufficiency_review_2026-09-29.md).

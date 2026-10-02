# G2 원문 관계 입력·실행 분리 — 2026-10-02

- #554. G1 독립 의미 검수에서 채택한 C 문단을 그대로 반영하고 recipe를 v32로 구분했다. 같은 저장 입력을 생산 make_prompt에 넣으면 사전 동결 C prompt와 정확히 일치한다. 추가 실제 모델 호출0.
- source_text Relation은 유형 ID를 선택하지 않는데도 Concept의 후보와 실패에 종속돼 있었다. process_group에서 Concept의 입력 정리 전 원문 문맥을 따로 보존하고, Relation에서는 일반 유형 후보 정보를 제외했다. 주원문·항·조건·표 문맥과 Scout/Concept 도구 원문을 기존 함수로 전달하며 실제 제공 원문의 dependency를 다시 계산한다.
- Concept 실패나 관측0이어도 기존 예산·입력 조건 안에서 Relation을 실행한다. Concept 실패 기록, Builder 보류와 전체 partial은 유지한다. Concept0 상태를 완화해 성공으로 바꾸지 않았다. Concept/Builder의 유형 비교, 복구의 이전 원관계·legacy 직접 끝점 정의는 유지했다.
- 독립 실행 검수에서 재개 결함을 발견했다. Concept 실패 뒤 Relation은 성공했는데, 재개된 Concept가 새 원문을 조회하면 성공 Relation의 입력 해시가 달라졌다. 성공 Relation은 저장 unit 전체와 dependency를 재사용하도록 수정했다. 새 자료는 새 Builder에 전달하며 최초 연결 Concept 단위 ID를 묶음에 고정해 성공 Builder의 입력도 바꾸지 않는다. 새 저장소·실행기·역할은 없다.
- 관련 계약·분석·복구139개 검사 통과(16.59초, 기존 직렬화 경고13개). Concept 정상/0/실패, Concept용 정리에서 제외된 도구 원문 보존, Builder에 관측/관계 도달, Concept 실패→재개 성공+새 원문→성공 Relation 불변/추가 호출0과 새 Builder dependency 전달을 확인했다.
- 기존 실패 회귀도 새로운 실행 책임에 맞췄다. 실패한 Concept 뒤 Relation과 명시적 Builder 보류를 저장하고, 재개해 Concept가 성공해도 이전의 성공한 보류는 뒤집지 않는다. 테스트 통과를 자동 초안 완성이나 모델 품질 재측정으로 계산하지 않는다.
- 다음은 G3 역할별 복구 비교자료 최소화와 독립 코드 검수, 최종 코드·새 동결의 G4 단일 C2 확인이다. 실제 사람0명/시간null/효용미측정. 현재 사용자 결정이 필요한 사항 없음.

## Builder 추가 문맥 한도 보완

- 독립 실행 검수에서 새 Concept 도구 원문을 Builder 조립 후 일괄 추가하면 입력 한도를 넘을 수 있음을 확인했다. 기존 add_retrieved/add_terms의 크기 검사·제외 경로로 바꿨다. 필수 후보 근거는 유지하고 추가 원문/용어만 여유 안에서 전달한다.
- 최초 선택한 추가 문맥·파생 dependency·용어를 기존 candidate_group에 고정하고 제외 원문/용어 ID를 기록한다. 재개 때 성공 Relation/Builder 입력은 그대로 사용한다. 변경된 계약은 v33으로 구분했다.
- 작은 실제 경계 검사2개 통과: 재개 Concept의 짧은 원문은 새 Builder에 전달, 긴 원문은 제외 사유 경로에 남고 Builder 입력 한도 유지, 두 경우 모두 다음 재개에서 추가 호출0·선택 문맥 불변. G3는 별도 작업·커밋이다.

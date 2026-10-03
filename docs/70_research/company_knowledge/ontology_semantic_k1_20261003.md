# K1: 호출·재개 간 참조 안정화

- 관련 이슈: #569, 상위 #534/#539
- 이유: J3 Revision에는 정확한 원문이 있었으나 Critic 자유문장의 이전 cN/sID와 새 호출의 별칭이 혼재했다. 입력 부족이 아닌 호출별 주소 변경 문제다.
- 변경: recipe v43/reference_contract=canonical-v1에서 후보·근거 canonical ID 유지. source_ref는 immutable block/span/text로 계산. make_prompt·fits·call이 같은 bind 경로 사용. 별도 참조 저장소나 자유문장 치환 없음.
- 보존: 과거 reference_contract 없는 호출은 기존 매핑·run/unit 주소 계약 유지. 실제 제공 원문 allowlist, 차단 근거 검사, 성공 단위 입력 해시 검사 유지. 과거 실행을 새 recipe로 자동 재해석하지 않음.
- 확인: 관련 5개 테스트 파일 179 통과, 기존 Pydantic serializer 경고 13개. 역할·목록 순서·제공 집합·재개 run 변경에도 동일 참조, 다른 블록/구간/본문 구별, 미제공 참조 거부 확인. 실제 모델 호출 0.
- 테스트 보완: canonical ID 순서와 무관하게 분류 수정 후 관계 끝점의 class 검증 실패를 검사. domain만 가정하던 검사를 실제 domain/range 어느 끝점이 수정됐는지에 독립적으로 변경.
- J3 보존: result.json SHA256 105afa6082cc7617205fe63706225c235322a1941dc12a00885a66331f6638bb, knowledge.db SHA256 98624edd180a624dfb9d0bffb4f68a5f2d1fcb39af10d53a5bee173d34d04d08 일치.
- 한계/다음: ID 안정화는 의미 품질 성공 증거가 아니다. K2에서 명제/연결 판정과 중복 내용 판단을 보완하며 실제 품질은 K4에서 측정한다. 현재 사용자 결정이 필요한 사항 없음.

# AGENTS.md

## 프로젝트 공통 완료 보고 규칙

모든 작업의 완료 보고에는 사용자가 파일을 별도로 열지 않아도 이해할 수 있도록 다음 내용을 설명한다.

- **진행 이유:** 왜 해당 범위·자료·방법을 선택했는지, 중요한 선택의 근거를 설명한다.
- **결과:** 무엇을 변경하거나 확인했고 어떤 결과가 나왔는지 설명한다. 완료·미완료, 실제 검증·추정, 한계를 구분한다.
- **다음 작업:** 다음에 해야 할 일과 그 이유를 구체적으로 제시한다.
- **사용자 결정 사항:** 사용자가 결정해야 할 선택과 영향을 명시한다. 필요한 결정이 없으면 '현재 사용자 결정이 필요한 사항 없음'이라고 밝힌다. 이미 승인된 범위나 일반적인 구현 선택은 불필요하게 재승인받지 않는다.

링크와 파일 목록만으로 설명을 대신하지 않는다. 작업 규모에 맞게 간결하게 작성하며, 이 규칙은 코드·조사·설계·문서 작업 모두에 적용한다.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

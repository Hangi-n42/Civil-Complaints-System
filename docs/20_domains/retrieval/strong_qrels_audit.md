# Strong LLM 검색 평가셋 감사 절차

## 목적

기존 `qrels_pooled_3judge.tsv`를 보존하면서, 강한 LLM으로 전체 8,057쌍을 다시 감사해 `qrels_pooled_strong_audit.tsv`를 만든다.

이 작업은 기존 로컬 3-judge 라벨을 폐기하는 것이 아니라, 더 강한 감사자 기준으로 라벨 흔들림을 확인하는 것이다.

## 1. Dry-run

API 호출 없이 출력 경로와 resume/checkpoint 동작만 확인한다.

```bash
python scripts/audit_qrels_with_strong_llm.py \
  --limit 20 \
  --dry-run \
  --checkpoint /tmp/strong_audit.jsonl \
  --out-qrels /tmp/qrels_pooled_strong_audit.tsv \
  --out-summary-json /tmp/strong_audit_summary.json \
  --out-summary-md /tmp/strong_audit_summary.md \
  --out-disagreements /tmp/strong_audit_disagreements.csv
```

## 2. Hosted strong LLM 감사

OpenAI-compatible Chat Completions API를 사용한다.

```bash
OPENAI_API_KEY=... \
STRONG_AUDIT_MODEL=gpt-4o \
python scripts/audit_qrels_with_strong_llm.py \
  --provider openai \
  --resume
```

기본 산출물은 다음과 같다.

- `data/evaluation/v3/checkpoints/strong_audit.jsonl`
- `data/evaluation/v3/qrels_pooled_strong_audit.tsv`
- `reports/retrieval/v3/strong_audit_summary.json`
- `reports/retrieval/v3/strong_audit_summary.md`
- `reports/retrieval/v3/strong_audit_disagreements.csv`

## 3. Tailscale 데스크톱 Ollama 감사

로컬 LLM을 다시 쓰거나 GPU가 필요한 대량 작업은 Tailscale 데스크톱에서 수행한다.

```bash
OLLAMA_BASE_URL=http://100.71.35.78:11434 \
python scripts/audit_qrels_with_strong_llm.py \
  --provider ollama \
  --model qwen2.5:14b \
  --resume
```

## 4. Strong-audit qrels 기준 재평가

감사 qrels 생성 후 metadata soft rerank 평가를 새 qrels 기준으로 다시 실행한다.

```bash
EMBEDDING_DEVICE=mps \
python scripts/eval_metadata_soft_rerank.py \
  --qrels-path data/evaluation/v3/qrels_pooled_strong_audit.tsv \
  --out-json reports/retrieval/v3/metadata_soft_rerank_eval_strong_audit.json \
  --out-md reports/retrieval/v3/metadata_soft_rerank_summary_strong_audit.md \
  --eval-set-label "qrels_pooled_strong_audit, NO-self"
```

기존 qrels 기준 결과와 새 qrels 기준 결과를 비교한다.

```bash
python scripts/write_qrels_shift_impact.py
```

산출물:

- `reports/retrieval/v3/qrels_shift_impact.md`

## 5. 해석 원칙

- 기존 `qrels_pooled_3judge.tsv` 결과는 `v3_local_3judge` baseline snapshot으로 보존한다.
- 새 `qrels_pooled_strong_audit.tsv` 결과는 강화된 rubric 기준 재평가로 본다.
- 두 평가셋에서 같은 방향으로 반복되는 결론만 안정적인 결론으로 채택한다.
- `rel2_downgrade_candidate`는 답변 초안 grounding 관점에서 가장 먼저 사람 리뷰해야 한다.


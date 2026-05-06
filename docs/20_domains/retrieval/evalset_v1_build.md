# 검색 평가셋 v1 생성 가이드

## 개요

`scripts/build_retrieval_eval_set_v1.py`는 legacy `evaluation_set.json`을 BEIR 호환 평가셋으로 변환한다.

생성 결과:

- `corpus.jsonl`
- `queries.jsonl`
- `qrels.tsv`
- `manifest.json`
- `smoke/queries.jsonl`
- `smoke/qrels.tsv`

## 실행 예시

```bash
python scripts/build_retrieval_eval_set_v1.py \
  --source "docs/40_delivery/week3/model_test_assets/evaluation_set.json" \
  --output-dir "data/eval/retrieval/v1" \
  --smoke-size 50
```

## 후속 평가 실행

```bash
python scripts/evaluate_retrieval.py \
  --eval-dir "data/eval/retrieval/v1" \
  --pipeline "configs/retrieval_pipelines/baseline_dense.yaml" \
  --output-dir "reports/retrieval" \
  --issue-number 200
```

## 주의사항

- `data/` 경로는 `.gitignore` 대상이므로 로컬 생성 파일은 기본적으로 버전 관리에 포함되지 않는다.
- 팀 공유가 필요하면 검토 완료된 스냅샷만 별도 공유 저장소나 아티팩트 스토리지에 업로드한다.
- relevance 기준 변경 시 `manifest.json`의 guideline도 함께 갱신한다.


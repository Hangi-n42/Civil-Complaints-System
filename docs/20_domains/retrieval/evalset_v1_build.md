# 검색 평가셋 v1 생성 가이드

## 개요

`scripts/build_retrieval_eval_set_v1.py`는 다음 두 입력을 BEIR 호환 평가셋으로 변환한다.

- legacy `evaluation_set.json` (`--source`)
- AI Hub 원천 JSON 디렉터리 (`--source-dir`)

생성 결과:

- `corpus.jsonl`
- `queries.jsonl`
- `qrels.tsv`
- `manifest.json`
- `smoke/queries.jsonl`
- `smoke/qrels.tsv`

## 실행 예시

### 1) AI Hub 원천 디렉터리에서 생성

```bash
python scripts/build_retrieval_eval_set_v1.py \
  --source-dir "C:/Projects/AI-Civil-Affairs-Systems/data/Civil_complaints_data" \
  --output-dir "data/eval/retrieval/v1" \
  --smoke-size 50 \
  --max-files 5000
```

### 2) legacy evaluation_set.json에서 생성

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
- 원천 데이터가 큰 경우 `--max-files`로 샘플링해 빠르게 초기 smoke 셋을 만든 뒤, 검토 완료 후 전체 생성으로 확장하는 것을 권장한다.
- v1 생성기는 `qid(현재 민원)`에 대해 **동일 문서(self docid)를 qrels에서 제외**하고, 같은 주제군 내 유사 과거 민원을 qrels로 구성한다.
- `queries.jsonl`의 `text`는 **4요소 구조(관찰/결과/요청/맥락)**로 생성되며, metadata에도 각 요소가 분리 저장된다.


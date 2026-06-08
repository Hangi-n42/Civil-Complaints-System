# ChromaDB Git LFS 검토

## 결론

`data/chroma_db/` 전체를 GitHub LFS에 올리는 방식은 현재 권장하지 않는다.

현재 운영 기본값은 다음과 같다.

- `data/chroma_db/`는 `.gitignore`에 계속 둔다.
- 검색 DB는 로컬에서 재인덱싱하거나 metadata 백필 스크립트로 재생성한다.
- 꼭 공유가 필요하면 GitHub Release artifact나 별도 스토리지에 압축본을 수동 업로드한다.
- LFS는 원천 데이터, 법령 사전, 학습 모델처럼 재생성 비용이 크고 변경 빈도가 낮은 파일에 우선 사용한다.

## 확인한 상태

- `.gitignore`는 `data/chroma_db/`를 제외한다.
- `.gitattributes`는 `data/raw_data/**`, `data/processed/**`, `data/laws/*.json`, `*.joblib`을 LFS 대상으로 둔다.
- 로컬 `data/chroma_db/` 크기는 약 137MB, 76개 파일이다.
- `civil_cases_v1`은 9,132건, `civil_cases_eval_v1`은 250건이다.

## LFS에 올리지 않는 이유

ChromaDB는 자주 바뀌는 바이너리 DB다. metadata만 바뀌어도 SQLite/HNSW 파일이 갱신될 수 있고, Git LFS에서는 새 버전 파일이 저장량과 다운로드 사용량에 영향을 준다.

GitHub 문서도 LFS 저장량과 bandwidth가 과금/쿼터 대상이며, 파일의 새 버전은 새 저장량으로 계산된다고 설명한다.

- GitHub Docs: https://docs.github.com/en/billing/concepts/product-billing/git-lfs

또한 ChromaDB에는 검색 metadata, snippet, 원문 일부가 들어갈 수 있다. 민원 데이터는 마스킹되었더라도 개인정보 검토가 필요하므로, DB 전체를 저장소에 넣는 방식은 노출 면적을 넓힌다.

## 권장 운영 방식

1. 원천 데이터와 법령 사전은 Git LFS로 관리한다.
2. `data/chroma_db/`는 로컬 산출물로 취급한다.
3. BE1 검색 신호가 추가된 경우 다음 명령으로 기존 Chroma metadata를 백필한다.

```bash
python scripts/backfill_chromadb_search_signals.py
```

4. 완전 재인덱싱이 필요하면 `docs/30_manuals/local_chromadb_indexing.md`의 절차를 따른다.
5. 팀원이 repo clone만으로 검색 DB까지 바로 받아야 한다는 요구가 생기면, LFS 전체 추적보다 압축 artifact 공유를 먼저 검토한다.

## 판단 기준

| 기준 | 현재 판단 |
| --- | --- |
| 재현성 | 코드와 LFS 원천 데이터로 재생성 가능해야 한다. |
| 비용/쿼터 | ChromaDB 전체 LFS 추적은 저장량과 다운로드 사용량 부담이 있다. |
| 안정성 | Chroma 버전, OS, HNSW 파일 상태에 따라 DB 호환성 문제가 생길 수 있다. |
| 보안/개인정보 | metadata와 원문 snippet 포함 가능성이 있어 저장소 추적은 신중해야 한다. |


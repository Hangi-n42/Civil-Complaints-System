# 검색 평가셋(qrels) 재구축 프로토콜 — LLM-silver 기준

> 2026-06-21 확정. 독립 AI 2회 교차검토로 수렴. 목표는 **절대 gold benchmark가 아니라
> 검색 variant 간 상대 비교 + 회귀 탐지**. "정답/ground truth" 대신 **LLM-silver qrels**로 명명.

## 배경
- 코퍼스 9,132 → 25,565 (정책 Q&A 16,433 추가) → 기존 qrels(9,132) 무효, pooling bias.
- 정책 Q&A를 PARANOID→STRICT 재색인(법령명 보존). STEP0에서 동결(`corpus_snapshot.json`).
- 핵심 약점: 사람 ground truth 0, LLM 자기검증(κ0.567)뿐 → **사람 anchor calibration이 관건**.

## 프로토콜
- **STEP0 코퍼스 동결** ✅ — 25,565, case=chunk 1:1, STRICT, 해시 잠금. 평가 중 변경 금지.
- **STEP1 쿼리셋** — version-neutral(민원 원문) 100 + 정책 Q&A 도메인 쿼리 N.
  정책 쿼리는 문서 복붙이 아니라 **의역**으로 leakage 차단. source(민원/정책)·유형별 stratify.
- **STEP2 pooling** — BM25/dense/hybrid/production/old-baseline/QA-only/case-only 각 top-50
  → near-dup dedup: **cosine + char n-gram/Jaccard + source_id 동일성**(한국어 paraphrase 대응).
- **STEP3 LLM judge** — Claude temp=0, 루브릭 v3.1(rel 0/1/2 + risk flags). **전수 1회 +
  경계/고영향/불일치 pair만 재판정**. 후보 순서 셔플(position bias). **근거 span 요구** +
  단순 주제 유사성 감점 규칙. 보조 LLM은 불일치 tie-break만.
- **STEP4 사람 anchor (필수, 최우선)** — 층화 80~120쌍(rel=2예상/1↔2경계/rel=0/LLM disagreement/
  정책 top hit/시스템 승패 바꾸는 pair). 지표: **binary κ(rel≥1) + rel=2 precision + Spearman ρ
  + confusion matrix**(3등급 κ는 80~120쌍에서 흔들리므로 단독 사용 금지). ρ<0.5면 judge 재설계,
  ≥0.6이면 상대 비교 신뢰. 목적은 "사람이 정답"이 아니라 **LLM 폐회로를 끊는 계측기**.
- **STEP5 qrels 3-way** — Silver-All(전체) / Leakage-Resistant(near-dup 제외) / Anchor-Audit(사람 검증분).
- **STEP6 지표** — paired ΔnDCG@10, **query 단위 block bootstrap 95% CI**, source×유형 slice,
  judged coverage, unjudged residual(top-50 밖 샘플 검사). **gain은 linear(0,1,2) primary +
  2^rel−1(0,1,3) sensitivity 둘 다** → 방향 일치하면 강한 신호, 갈리면 "rel=2 판정 민감" 보고.
  high-conf subset은 selection bias 진단용(vs Silver-All 격차 보고), headline 아님.
- **STEP7 리포트** — 전 caveat 명시 + "LLM-silver" 명명 + anchor ρ/κ 수치 동봉.

## 필수 caveat
LLM-silver(사람 anchor N=○○, ρ=○○) · 절대값 금지 paired Δ만 · unjudged=rel0 가정(coverage ○○%)
· near-dup 잔존 가능(Leakage-Resistant 병기) · 단일 judge 단일 bias · 1↔2 경계 불안정(κ○○).

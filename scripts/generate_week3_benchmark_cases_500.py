"""Week3 벤치마크 케이스 500건 확장 생성 스크립트.

기존 seed 케이스를 기반으로 query/context 변형을 적용해
재현 가능한 대규모 벤치마크 세트를 생성한다.

Usage:
  python scripts/generate_week3_benchmark_cases_500.py \
    --input docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json \
        --output docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json \
    --target 500 \
    --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent

QUERY_PREFIXES = [
    "담당자 검토용으로",
    "현장 대응 관점에서",
    "민원 처리 표준에 맞춰",
    "근거 중심으로",
    "주요 리스크를 포함해",
    "행정 실행 가능성을 고려해",
]

QUERY_SUFFIXES = [
    "핵심만 간단히 정리해줘.",
    "우선순위를 포함해 답해줘.",
    "실행 가능한 형태로 제시해줘.",
    "근거 청크 기준으로 설명해줘.",
    "즉시 대응과 후속 대응을 분리해줘.",
    "담당자 안내문 스타일로 작성해줘.",
]

ADDITIONAL_CONSTRAINTS = [
    "답변은 5문장 이내로 제한해줘.",
    "불확실한 내용은 limitations로 분리해줘.",
    "citations를 최소 2개 포함해줘.",
    "다중 요청 여부를 먼저 판단해줘.",
    "시간 민감도를 반영해서 우선순위를 정해줘.",
    "행정 단위 기준으로 조치 주체를 구분해줘.",
]

SNIPPET_PREFIXES = [
    "현장 보고에 따르면",
    "민원 기록 기준",
    "최근 접수 이력에서",
    "담당 부서 확인 결과",
    "유사 사례 분석상",
]

SNIPPET_SUFFIXES = [
    "조속한 조치 요구가 반복되고 있음.",
    "주민 불편 체감이 높아지는 추세임.",
    "재발 방지 대책 수립 필요성이 제기됨.",
    "현장 확인과 행정 안내가 함께 필요함.",
    "우선 대응 기준 정립이 필요함.",
]


def _load_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: Path, data: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _mutate_query(base_query: str, rng: random.Random, idx: int) -> str:
    prefix = QUERY_PREFIXES[idx % len(QUERY_PREFIXES)]
    suffix = QUERY_SUFFIXES[(idx // 3) % len(QUERY_SUFFIXES)]
    constraint = ADDITIONAL_CONSTRAINTS[(idx // 5) % len(ADDITIONAL_CONSTRAINTS)]

    q = base_query.strip()
    if not q.endswith((".", "?", "!", "다")):
        q = q + "."

    # 일부 케이스는 제약 조건을 추가해 난이도를 높인다.
    if idx % 2 == 0:
        return f"{prefix} {q} {suffix} {constraint}"
    return f"{prefix} {q} {suffix}"


def _mutate_snippet(snippet: str, rng: random.Random, idx: int) -> str:
    prefix = SNIPPET_PREFIXES[(idx + 1) % len(SNIPPET_PREFIXES)]
    suffix = SNIPPET_SUFFIXES[(idx + 2) % len(SNIPPET_SUFFIXES)]
    core = snippet.strip().rstrip(".")
    if idx % 3 == 0:
        return f"{prefix} {core}. {suffix}"
    if idx % 3 == 1:
        return f"{core}. {suffix}"
    return f"{prefix} {core}."


def _mutate_score(score: float, rng: random.Random) -> float:
    jitter = rng.uniform(-0.03, 0.03)
    new_score = max(0.5, min(0.99, score + jitter))
    return round(new_score, 2)


def _build_case(base: Dict[str, Any], idx: int, rng: random.Random) -> Dict[str, Any]:
    case = deepcopy(base)
    case["case_id"] = f"BENCHX-{idx:04d}"
    case["query"] = _mutate_query(str(base.get("query", "")), rng, idx)

    context = case.get("context", [])
    for c_idx, c in enumerate(context):
        c["chunk_id"] = f"{c.get('case_id', 'CASE-UNK')}__chunk-{c_idx + 1}"
        c["snippet"] = _mutate_snippet(str(c.get("snippet", "")), rng, idx + c_idx)
        c["score"] = _mutate_score(float(c.get("score", 0.8)), rng)

    # 일부 케이스는 시급성 변형을 통해 분포를 넓힌다.
    if idx % 7 == 0:
        case["time_sensitivity"] = "high"
    elif idx % 7 == 3:
        case["time_sensitivity"] = "low"

    # multi_request 분포 변형
    if idx % 5 == 0:
        case["requires_multi_request"] = True

    return case


def generate_expanded_cases(
    seed_cases: List[Dict[str, Any]],
    target: int,
    seed: int,
) -> List[Dict[str, Any]]:
    if not seed_cases:
        raise ValueError("seed 케이스가 비어 있습니다.")

    rng = random.Random(seed)

    expanded: List[Dict[str, Any]] = []

    for idx in range(1, target + 1):
        base = seed_cases[(idx - 1) % len(seed_cases)]
        case = _build_case(base, idx, rng)
        expanded.append(case)

    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(description="Week3 벤치마크 케이스 500건 확장 생성")
    parser.add_argument(
        "--input",
        type=str,
        default="docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json",
        help="seed 케이스 파일 경로",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json",
        help="확장 케이스 출력 경로",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=500,
        help="생성 목표 건수",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="재현 가능한 생성용 seed",
    )
    args = parser.parse_args()

    input_path = (PROJECT_ROOT / args.input).resolve()
    output_path = (PROJECT_ROOT / args.output).resolve()

    seed_cases = _load_json(input_path)
    expanded = generate_expanded_cases(seed_cases=seed_cases, target=args.target, seed=args.seed)
    _dump_json(output_path, expanded)

    print(f"[DONE] input={input_path}")
    print(f"[DONE] output={output_path}")
    print(f"[DONE] generated={len(expanded)}")


if __name__ == "__main__":
    main()

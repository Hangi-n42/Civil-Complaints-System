#!/usr/bin/env python3
"""
랜덤 샘플링 스크립트

사용법:
  python scripts/sample_raw_data.py --n 500

옵션:
  --src    데이터 폴더 (기본: data/raw_data)
  --out    출력 파일 경로 (기본: data/raw_data/sample_500.json)
  --n      샘플 개수 (기본: 500)
  --seed   랜덤 시드 (선택)

동작:
  - JSON 배열, 단일 JSON 객체, 또는 NDJSON 형식을 지원합니다.
  - 메모리 절약을 위해 리저버 샘플링(reservoir sampling)을 사용합니다.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Iterator, Any


def iter_records_from_file(path: Path) -> Iterator[Any]:
    """주어진 파일에서 레코드를 반복적으로 반환한다.
    파일이 JSON 배열이면 배열의 각 요소, 단일 객체이면 그 객체,
    아니면 각 라인을 JSON으로 파싱(일반적인 NDJSON)한다.
    """
    text = path.read_text(encoding="utf-8")
    try:
        obj = json.loads(text)
    except Exception:
        # NDJSON 시도
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                # 무시하고 계속
                continue
        return

    if isinstance(obj, list):
        for item in obj:
            yield item
    elif isinstance(obj, dict):
        # 단일 객체라면 하나의 레코드로 간주
        yield obj
    else:
        # 알 수 없는 형식은 무시
        return


def iter_all_records(src_dir: Path) -> Iterator[Any]:
    for path in sorted(src_dir.glob("*.json")):
        try:
            yield from iter_records_from_file(path)
        except Exception:
            # 특정 파일 읽기 실패해도 전체는 계속 진행
            continue


def reservoir_sample(iterator: Iterator[Any], k: int, seed: int | None = None) -> list:
    if seed is not None:
        random.seed(seed)
    reservoir: list = []
    for i, item in enumerate(iterator):
        if i < k:
            reservoir.append(item)
        else:
            j = random.randrange(i + 1)
            if j < k:
                reservoir[j] = item
    return reservoir


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path, default=Path("data/raw_data"))
    p.add_argument("--out", type=Path, default=Path("data/raw_data/sample_500.json"))
    p.add_argument("--split-dir", type=Path, default=Path("data/urgency_500"),
                   help="Directory to write individual JSON files. If set, writes each sample to a separate file.")
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()

    src = args.src
    if not src.exists() or not src.is_dir():
        raise SystemExit(f"소스 디렉토리를 찾을 수 없습니다: {src}")

    it = iter_all_records(src)
    sample = reservoir_sample(it, args.n, seed=args.seed)
    # split-dir가 설정되어 있으면 각 레코드를 개별 파일로 저장
    split_dir = args.split_dir
    if split_dir:
        split_dir.mkdir(parents=True, exist_ok=True)
        for idx, rec in enumerate(sample, start=1):
            fname = f"{idx:06d}.json"
            try:
                with (split_dir / fname).open("w", encoding="utf-8") as f:
                    json.dump(rec, f, ensure_ascii=False, indent=2)
            except Exception:
                # 실패한 파일은 건너뜀
                continue
        print(f"샘플링 완료: {len(sample)}건을 {split_dir}에 개별 파일로 저장했습니다.")
    else:
        out = args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
        print(f"샘플링 완료: 전체 샘플 {len(sample)}건을 {out}에 저장했습니다.")


if __name__ == "__main__":
    main()

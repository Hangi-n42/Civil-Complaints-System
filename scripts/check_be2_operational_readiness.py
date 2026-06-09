"""BE2 검색 readiness 운영 스모크 체크.

기존 점검 스크립트를 얇게 묶어 운영 전/인수인계 후 재현 가능한 확인 절차를 제공한다.
민원 원문, 검색 snippet, 생성 답변 미리보기는 리포트에 기록하지 않는다.

  python scripts/check_be2_operational_readiness.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class CheckResult:
    name: str
    command: str
    ok: bool
    note: str


def _run_command(name: str, command: list[str], note: str) -> CheckResult:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    status = "통과" if proc.returncode == 0 else "실패"
    print(f"[{status}] {name}")
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).splitlines()[-8:])
        if tail:
            print(tail)
    return CheckResult(
        name=name,
        command=" ".join("python" if part == sys.executable else part for part in command),
        ok=proc.returncode == 0,
        note=note if proc.returncode == 0 else "실패: 터미널 출력의 오류 메시지 확인",
    )


def _check_citation_policy() -> CheckResult:
    from app.generation.citation.legal_citation import ground_legal_citations

    retrieved_articles = [
        {
            "law_name": "건축법",
            "article_no": "제80조",
            "law_id": "001823",
            "doc_type": "law",
            "source_url": "https://internal.example/source",
            "text": "제80조(이행강제금) 허가권자는 이행강제금을 부과할 수 있다.",
        }
    ]
    result = ground_legal_citations(
        "건축법 제80조에 따라 검토합니다. 건축법 제999조도 검토합니다.",
        retrieved_articles,
    )

    valid = result.get("valid") or []
    invalid = result.get("invalid") or []
    ok = (
        len(valid) == 1
        and valid[0].get("public_url")
        and "source_url" not in valid[0]
        and invalid
        and all("source_url" not in item for item in invalid)
    )
    status = "통과" if ok else "실패"
    print(f"[{status}] citation 공개 URL 정책")
    return CheckResult(
        name="citation 공개 URL 정책",
        command="ground_legal_citations() fixture assert",
        ok=ok,
        note=(
            "valid citation은 public_url만 포함하고 source_url은 제거됨"
            if ok
            else "public_url/source_url 정책 불일치"
        ),
    )


def _render_report(results: list[CheckResult], *, tmp_dir: Path) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    overall = "통과" if all(result.ok for result in results) else "실패"
    lines = [
        "# BE2 검색 readiness 운영 스모크 체크 리포트",
        "",
        f"- 생성 시각(UTC): `{generated_at}`",
        "- 관련 이슈: #352",
        f"- 전체 결과: **{overall}**",
        f"- 상세 산출물 위치: `{tmp_dir}`",
        "",
        "## 확인 항목",
        "",
        "| 항목 | 결과 | 실행 명령/검증 | 비고 |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        status = "통과" if result.ok else "실패"
        lines.append(
            f"| {result.name} | {status} | `{result.command}` | {result.note} |"
        )

    lines += [
        "",
        "## 운영 판단 기준",
        "",
        "- ChromaDB `civil_cases_v1`의 검색 신호 metadata 적재율을 확인한다.",
        "- 법령 조문 collection `law_articles_v1`가 존재하고 대표 질의 검색/인용검증이 통과해야 한다.",
        "- 공개 응답 citation에는 `source_url`을 노출하지 않고 `public_url`만 남아야 한다.",
        "- 민원 원문, 검색 snippet, 생성 답변 미리보기 등 개인정보 위험 raw 산출물은 커밋하지 않는다.",
        "",
        "## 남은 리스크 확인",
        "",
        "- `entity_texts` 적재율이 낮으면 객체명 기반 rerank 효과는 제한적으로 해석한다.",
        "- `responsible_units`는 fallback 값일 수 있으므로 확정 담당부서처럼 해석하지 않는다.",
        "- 법령 grounding 이후 `fast_fallback` 증가는 BE3 생성 안정성 이슈로 분리해 본다.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="BE2 검색 readiness 운영 스모크 체크")
    parser.add_argument("--persist-dir", default="data/chroma_db")
    parser.add_argument("--collection", default="civil_cases_v1")
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체 collection 점검")
    parser.add_argument("--tmp-dir", default="/tmp/be2_operational_smoke_check")
    parser.add_argument(
        "--out-md",
        default="reports/retrieval/v3/be2_operational_smoke_check.md",
        help="스모크 체크 요약 리포트 경로",
    )
    args = parser.parse_args()

    tmp_dir = Path(args.tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    coverage_json = tmp_dir / "chromadb_search_signal_metadata_coverage.json"
    coverage_md = tmp_dir / "chromadb_search_signal_metadata_coverage.md"

    results = [
        _run_command(
            "ChromaDB 검색 신호 metadata 적재율",
            [
                sys.executable,
                "scripts/check_chromadb_search_signal_coverage.py",
                "--persist-dir",
                args.persist_dir,
                "--collection",
                args.collection,
                "--limit",
                str(max(0, args.limit)),
                "--out-json",
                str(coverage_json),
                "--out-md",
                str(coverage_md),
            ],
            f"민감 필드는 해시 처리, 상세 리포트는 {tmp_dir}에 저장",
        ),
        _run_command(
            "법령 조문 인덱스",
            [sys.executable, "scripts/check_law_index.py"],
            "`law_articles_v1` 대표 질의 검색과 인용검증 확인",
        ),
        _check_citation_policy(),
    ]

    out_md = ROOT / args.out_md
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render_report(results, tmp_dir=tmp_dir), encoding="utf-8")
    print(f"[리포트] {out_md}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

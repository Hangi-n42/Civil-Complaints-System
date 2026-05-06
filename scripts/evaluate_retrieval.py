import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.evaluation.artifacts import write_jsonl, write_trec_run
from app.evaluation.datasets import load_eval_dataset, load_legacy_evaluation_set, sha256_file
from app.evaluation.metrics import RunRecord, evaluate_run
from app.evaluation.reporting import append_run_summary, build_gate, latency_summary
from app.evaluation.slices import evaluate_slices
from app.retrieval.pipeline.runner import RetrievalPipelineRunner, load_pipeline_spec


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="통합 검색 평가 실행기")
    parser.add_argument("--eval-dir", type=str, help="corpus.jsonl, queries.jsonl, qrels.tsv가 있는 평가셋 디렉터리")
    parser.add_argument("--legacy-eval-set", type=str, help="기존 evaluation_set.json 경로")
    parser.add_argument("--pipeline", type=str, required=True, help="검색 파이프라인 YAML 명세 경로")
    parser.add_argument("--output-dir", type=str, default="reports/retrieval")
    parser.add_argument("--run-id", type=str, default="")
    parser.add_argument("--issue-number", type=str, default="198")
    parser.add_argument("--sample-size", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.eval_dir and not args.legacy_eval_set:
        raise SystemExit("--eval-dir 또는 --legacy-eval-set 중 하나는 반드시 필요합니다")

    dataset = (
        load_eval_dataset(args.eval_dir)
        if args.eval_dir
        else load_legacy_evaluation_set(args.legacy_eval_set, sample_size=args.sample_size)
    )
    queries = dataset.queries[: args.sample_size] if args.sample_size > 0 and args.eval_dir else dataset.queries
    allowed_qids = {query.qid for query in queries}
    qrels = [qrel for qrel in dataset.qrels if qrel.qid in allowed_qids]

    spec = load_pipeline_spec(args.pipeline)
    run_id = args.run_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{spec.pipeline_id}"
    output_dir = Path(args.output_dir)
    artifact_dir = output_dir / "artifacts" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    runner = RetrievalPipelineRunner(spec)
    results = runner.run_sync(queries)

    final_run: list[RunRecord] = []
    stage_runs: dict[str, list[RunRecord]] = {}
    for result in results:
        for output in result.stage_outputs.values():
            stage_rows = [doc.to_run_record() for doc in output.candidates]
            stage_runs.setdefault(output.stage_name, []).extend(stage_rows)
        final_run.extend(doc.to_run_record() for doc in result.final_docs)

    stage_artifacts: dict[str, str] = {}
    for stage_name, rows in stage_runs.items():
        path = artifact_dir / f"{stage_name}.trec"
        write_trec_run(path, rows, run_name=stage_name)
        stage_artifacts[stage_name] = str(path)

    final_path = artifact_dir / "final.trec"
    write_trec_run(final_path, final_run, run_name="final")
    write_jsonl(artifact_dir / "queries.jsonl", queries)
    stage_artifacts["final"] = str(final_path)

    metrics = evaluate_run(qrels, final_run)
    slice_metrics = evaluate_slices(queries, qrels, final_run)
    latency_ms = latency_summary([result.latency_ms for result in results])
    gate = build_gate(metrics, latency_ms)

    summary = {
        "run_id": run_id,
        "issue_number": str(args.issue_number),
        "branch": _git_value(["branch", "--show-current"]),
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "pipeline_id": spec.pipeline_id,
        "pipeline_hash": spec.pipeline_hash,
        "pipeline_path": str(spec.source_path) if spec.source_path else "",
        "eval_set_hash": dataset.eval_set_hash,
        "seed": spec.seed,
        "stage_artifacts": stage_artifacts,
        "metrics": {key: round(value, 4) for key, value in metrics.items()},
        "slice_metrics": slice_metrics,
        "latency_ms": latency_ms,
        "gate": gate,
        "evaluation": {"total_queries": len(queries), "total_qrels": len(qrels)},
    }
    if spec.source_path:
        summary["pipeline_file_hash"] = sha256_file(spec.source_path)

    report_path = artifact_dir / "summary.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    append_run_summary(output_dir / "runs.jsonl", summary)

    print(json.dumps(summary["metrics"], ensure_ascii=False, indent=2))
    print(f"[OK] run_id={run_id}")
    print(f"[OK] 리포트={report_path}")
    return 0 if gate["all_passed"] else 1


def _git_value(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


if __name__ == "__main__":
    sys.exit(main())

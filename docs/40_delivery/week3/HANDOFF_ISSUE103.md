# Week3 Issue #103 Handoff

## Scope
- Repository baseline: `main` + this handoff branch.
- Issue #101 and #102 are already merged/closed and must be treated as fixed baseline.
- Complete Issue #103 end-to-end on a higher-spec local machine.
- Include `candidate_ax4_light` benchmark execution.

## Required References
- `.github/agents/week3/BE2_QUICKSTART.md`
- `.github/agents/week3/be2_issue92_103_specification.md`
- `docs/40_delivery/week3/model_benchmark_protocol.md`
- `configs/week3_model_benchmark.yaml`

## Current Known Context
- `candidate_ax4_light` model detection was adjusted for Ollama tag format.
- On lower-spec local, generation timeout occurred due to long inference latency.
- A dedicated wait-and-run helper exists: `scripts/wait_and_benchmark_ax4.py`.

## Execution Checklist (Target Local)
1. Verify model install and availability in Ollama.
2. Re-run retrieval metrics for Issue #103-1/2/3.
3. Run `candidate_ax4_light` benchmark (Issue #103-4).
4. Update analysis report (Issue #103-5).
5. Confirm output artifacts below.

## Suggested Commands
```powershell
# 1) Verify environment
python -c "import yaml, httpx; print('deps ok')"

# 2) Retrieval metrics (if script exists in your flow)
python scripts/evaluate_retrieval.py

# 3) Model benchmark (ax4)
python scripts/run_week3_model_benchmark.py --config configs/week3_model_benchmark.yaml --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json --output-dir logs/evaluation/week3 --model candidate_ax4_light

# Optional helper for long install/wait cycle
python scripts/wait_and_benchmark_ax4.py
```

## Required Artifacts
- `logs/evaluation/week3/retrieval_metrics.json`
- `logs/evaluation/week3/model_benchmark_candidate_ax4_light.json`
- `docs/40_delivery/week3/be2_week3_analysis_report.md`

## Completion Criteria
- Retrieval metrics include Recall@5/Recall@10/latency.
- AX4 benchmark file is generated with parsable summary.
- Analysis report explains metric gap, risks, and next actions.

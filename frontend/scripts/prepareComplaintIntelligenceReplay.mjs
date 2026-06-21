import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const repoRoot = resolve(frontendRoot, "..");
const prepareScript = join(repoRoot, "scripts", "prepare_complaint_intelligence_real_replay.py");
const defaultInput = "C:\\Projects\\AI-Civil-Affairs-Systems\\data\\processed";

const python = findPython();
const input = process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_INPUT || defaultInput;
const args = [
  prepareScript,
  "--input",
  input,
  "--min-events-per-scenario",
  process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_MIN_PER_SCENARIO || "20",
  "--max-events-per-scenario",
  process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_MAX_PER_SCENARIO || "20",
];

console.log("[predev] Complaint Intelligence real_replay seed/run-analysis 준비를 시작합니다.");
const result = spawnSync(python, args, {
  cwd: repoRoot,
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(`[predev] Python 실행 실패: ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) {
  console.error(`[predev] real_replay 준비 실패: exit ${result.status}`);
  process.exit(result.status ?? 1);
}
console.log("[predev] real_replay 준비가 완료되었습니다.");

function findPython() {
  const candidates = [
    process.env.CIVIL_PYTHON,
    join(repoRoot, "civil", "Scripts", "python.exe"),
    join(repoRoot, ".venv", "Scripts", "python.exe"),
    "C:\\Projects\\AI-Civil-Affairs-Systems\\civil\\Scripts\\python.exe",
    join(repoRoot, ".venv", "bin", "python"),
    "python",
    "python3",
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (candidate.includes("\\") || candidate.includes("/")) {
      if (existsSync(candidate)) return candidate;
      continue;
    }
    const probe = spawnSync(candidate, ["--version"], { stdio: "ignore", shell: false });
    if (probe.status === 0) return candidate;
  }
  throw new Error("사용 가능한 Python 실행 파일을 찾지 못했습니다. CIVIL_PYTHON 환경변수를 지정하세요.");
}

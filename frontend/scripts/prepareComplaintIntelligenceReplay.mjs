import { existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const repoRoot = resolve(frontendRoot, "..");
const prepareScript = join(repoRoot, "scripts", "prepare_complaint_intelligence_real_replay.py");
const seedPath = join(repoRoot, "data", "complaint_intelligence", "complaint_intelligence_real_replay_events.json");

const python = findPython();
const args = [
  prepareScript,
  "--min-events-per-scenario",
  process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_MIN_PER_SCENARIO || "20",
  "--max-events-per-scenario",
  process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_MAX_PER_SCENARIO || "20",
];
const input = findReplayInput();
if (input) {
  args.push("--input", input);
  console.log(`[predev] real_replay 입력 경로: ${input}`);
} else {
  args.push("--skip-build");
  console.log("[predev] 입력 원천을 찾지 못해 기존 real_replay seed로 DB만 준비합니다.");
}
if (process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_ALLOW_SYNTHETIC_FILL) {
  args.push("--allow-synthetic-fill", process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_ALLOW_SYNTHETIC_FILL);
}

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

function findReplayInput() {
  const candidates = [
    process.env.COMPLAINT_INTELLIGENCE_REAL_REPLAY_INPUT,
    join(repoRoot, "data", "processed"),
    join(repoRoot, "scripts", "data"),
    "C:\\Projects\\AI-Civil-Affairs-Systems\\data\\processed",
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (hasAnyFile(candidate)) {
      return candidate;
    }
  }

  if (!existsSync(seedPath)) {
    console.warn("[predev] 기존 real_replay seed도 없습니다. 데이터 원천 경로를 확인하세요.");
  }
  return null;
}

function hasAnyFile(path) {
  try {
    const stat = statSync(path);
    if (stat.isFile()) return true;
    if (!stat.isDirectory()) return false;
    return directoryHasAnyFile(path);
  } catch {
    return false;
  }
}

function directoryHasAnyFile(path) {
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const child = join(path, entry.name);
    if (entry.isFile()) return true;
    if (entry.isDirectory() && directoryHasAnyFile(child)) return true;
  }
  return false;
}

function findPython() {
  const candidates = [
    process.env.CIVIL_PYTHON,
    join(repoRoot, "civil", "Scripts", "python.exe"),
    join(repoRoot, ".venv", "Scripts", "python.exe"),
    "C:\\Projects\\AI-Civil-Affairs-Systems\\civil\\Scripts\\python.exe",
    join(repoRoot, ".venv", "bin", "python"),
    "/opt/homebrew/Caskroom/miniforge/base/bin/python",
    "python",
    "python3",
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (candidate.includes("\\") || candidate.includes("/")) {
      if (existsSync(candidate) && isSupportedPython(candidate)) return candidate;
      continue;
    }
    if (isSupportedPython(candidate)) return candidate;
  }
  throw new Error("Python 3.10 이상 실행 파일을 찾지 못했습니다. CIVIL_PYTHON 환경변수를 지정하세요.");
}

function isSupportedPython(candidate) {
  const probe = spawnSync(
    candidate,
    ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"],
    { stdio: "ignore", shell: false },
  );
  return probe.status === 0;
}

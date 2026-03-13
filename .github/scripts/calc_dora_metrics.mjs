import { writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

const owner = process.env.GITHUB_REPOSITORY_OWNER;
const repo = process.env.GITHUB_REPOSITORY?.split("/")[1];
const token = process.env.GITHUB_TOKEN;
const days = Number(process.env.DORA_WINDOW_DAYS || "30");
const incidentLabel = process.env.DORA_INCIDENT_LABEL || "incident";
const defaultBranch = process.env.GITHUB_DEFAULT_BRANCH || "main";

if (!owner || !repo || !token) {
  throw new Error("Missing required environment variables for GitHub API access.");
}

const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

async function gh(path) {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GitHub API error ${res.status} on ${path}: ${text}`);
  }

  return res.json();
}

async function ghPaginate(pathPrefix, limitPages = 10) {
  const all = [];
  for (let page = 1; page <= limitPages; page += 1) {
    const data = await gh(`${pathPrefix}${pathPrefix.includes("?") ? "&" : "?"}per_page=100&page=${page}`);
    if (!Array.isArray(data) || data.length === 0) break;
    all.push(...data);
    if (data.length < 100) break;
  }
  return all;
}

function avg(nums) {
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function median(nums) {
  if (!nums.length) return null;
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) return (sorted[mid - 1] + sorted[mid]) / 2;
  return sorted[mid];
}

function round(value, digits = 2) {
  if (value === null || Number.isNaN(value)) return null;
  const p = 10 ** digits;
  return Math.round(value * p) / p;
}

async function collectLeadTimeHours() {
  const prs = await ghPaginate(`/repos/${owner}/${repo}/pulls?state=closed&sort=updated&direction=desc`, 20);
  const merged = prs.filter((pr) => pr.merged_at && new Date(pr.merged_at) >= since);

  const leadTimes = [];
  for (const pr of merged) {
    const commits = await ghPaginate(`/repos/${owner}/${repo}/pulls/${pr.number}/commits`, 5);
    const commitDates = commits
      .map((c) => c?.commit?.author?.date)
      .filter(Boolean)
      .map((d) => new Date(d));

    const start = commitDates.length ? new Date(Math.min(...commitDates.map((d) => d.getTime()))) : new Date(pr.created_at);
    const end = new Date(pr.merged_at);
    const hours = (end.getTime() - start.getTime()) / (1000 * 60 * 60);
    if (hours >= 0) leadTimes.push(hours);
  }

  return {
    sample_size: leadTimes.length,
    mean_hours: round(avg(leadTimes)),
    median_hours: round(median(leadTimes)),
    p95_hours: round(
      leadTimes.length
        ? [...leadTimes].sort((a, b) => a - b)[Math.min(leadTimes.length - 1, Math.floor(leadTimes.length * 0.95))]
        : null,
    ),
  };
}

async function collectDeploymentStats() {
  const deployments = await ghPaginate(`/repos/${owner}/${repo}/deployments?ref=${encodeURIComponent(defaultBranch)}`, 20);
  const recent = deployments.filter((d) => new Date(d.created_at) >= since);

  let success = 0;
  let failed = 0;

  for (const dep of recent) {
    const statuses = await ghPaginate(`/repos/${owner}/${repo}/deployments/${dep.id}/statuses`, 2);
    const latest = statuses[0];
    const state = latest?.state;
    if (state === "success") success += 1;
    if (state === "failure" || state === "error") failed += 1;
  }

  const totalClassified = success + failed;
  const perDay = days > 0 ? success / days : null;
  const cfr = totalClassified > 0 ? (failed / totalClassified) * 100 : null;

  return {
    deployment_events_in_window: recent.length,
    successful_deployments: success,
    failed_deployments: failed,
    deployment_frequency_per_day: round(perDay),
    change_failure_rate_percent: round(cfr),
  };
}

async function collectMttrHours() {
  const issues = await ghPaginate(
    `/repos/${owner}/${repo}/issues?state=closed&labels=${encodeURIComponent(incidentLabel)}&sort=updated&direction=desc`,
    20,
  );

  const incidents = issues.filter((i) => !i.pull_request && i.closed_at && new Date(i.closed_at) >= since);
  const durations = incidents
    .map((i) => (new Date(i.closed_at).getTime() - new Date(i.created_at).getTime()) / (1000 * 60 * 60))
    .filter((h) => h >= 0);

  return {
    sample_size: durations.length,
    mean_hours: round(avg(durations)),
    median_hours: round(median(durations)),
  };
}

const leadTime = await collectLeadTimeHours();
const deploy = await collectDeploymentStats();
const mttr = await collectMttrHours();

const report = {
  generated_at: new Date().toISOString(),
  repository: `${owner}/${repo}`,
  window_days: days,
  assumptions: {
    lead_time: "first commit in merged PR -> merge time",
    deployment_frequency: `count of successful GitHub Deployment events on ref ${defaultBranch}`,
    mttr: `closed issues with label '${incidentLabel}' (created -> closed)` ,
    change_failure_rate: "failed deployments / (successful + failed deployments)",
  },
  metrics: {
    lead_time_for_changes: leadTime,
    deployment_frequency: {
      per_day: deploy.deployment_frequency_per_day,
      successful_deployments: deploy.successful_deployments,
      total_deployment_events: deploy.deployment_events_in_window,
    },
    mean_time_to_recovery: mttr,
    change_failure_rate: {
      percent: deploy.change_failure_rate_percent,
      failed_deployments: deploy.failed_deployments,
      classified_deployments: deploy.successful_deployments + deploy.failed_deployments,
    },
  },
};

const outputPath = "artifacts/dora/dora_metrics_latest.json";
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf-8");

const summary = `## DORA Metrics (${days}d)\n\n`
  + `- Lead Time for Changes (mean h): **${leadTime.mean_hours ?? "N/A"}** (n=${leadTime.sample_size})\n`
  + `- Deployment Frequency (successful/day): **${deploy.deployment_frequency_per_day ?? "N/A"}** (success=${deploy.successful_deployments})\n`
  + `- Mean Time to Recovery (mean h): **${mttr.mean_hours ?? "N/A"}** (n=${mttr.sample_size})\n`
  + `- Change Failure Rate (%): **${deploy.change_failure_rate_percent ?? "N/A"}** (failed=${deploy.failed_deployments})\n\n`
  + `Saved JSON: ${outputPath}`;

if (process.env.GITHUB_STEP_SUMMARY) {
  writeFileSync(process.env.GITHUB_STEP_SUMMARY, `${summary}\n`, { flag: "a" });
}

console.log(JSON.stringify(report, null, 2));

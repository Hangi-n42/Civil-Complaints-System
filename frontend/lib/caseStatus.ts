import { readJsonFromLocalStorage, sanitizeCaseStatuses } from "./safe-data";

export const CASE_STATUS_STORAGE_KEY = "case-status-overrides";
export const MAX_CASE_STATUS_STORAGE_BYTES = 24 * 1024;

export function loadCaseStatusOverrides(allowedCaseIds?: string[]): Record<string, string> {
  const parsed = readJsonFromLocalStorage<Record<string, string>>(CASE_STATUS_STORAGE_KEY, {
    maxBytes: MAX_CASE_STATUS_STORAGE_BYTES,
    removeOnOversize: true,
  });

  if (!parsed) {
    return {};
  }

  const allowed = allowedCaseIds && allowedCaseIds.length > 0 ? allowedCaseIds : Object.keys(parsed);
  return sanitizeCaseStatuses(parsed, allowed);
}

export function persistCaseStatusOverrides(
  nextStatuses: Record<string, string>,
  allowedCaseIds?: string[],
): Record<string, string> {
  if (typeof window === "undefined") {
    return {};
  }

  const allowed = allowedCaseIds && allowedCaseIds.length > 0 ? allowedCaseIds : Object.keys(nextStatuses);
  const sanitized = sanitizeCaseStatuses(nextStatuses, allowed);
  const serialized = JSON.stringify(sanitized);

  if (serialized.length > MAX_CASE_STATUS_STORAGE_BYTES) {
    window.localStorage.removeItem(CASE_STATUS_STORAGE_KEY);
    return {};
  }

  window.localStorage.setItem(CASE_STATUS_STORAGE_KEY, serialized);
  return sanitized;
}

export function persistCaseStatusSubset(
  nextSubset: Record<string, string>,
  managedCaseIds: string[],
): Record<string, string> {
  const currentStatuses = loadCaseStatusOverrides();
  const managed = new Set(managedCaseIds);
  const preservedStatuses = Object.fromEntries(
    Object.entries(currentStatuses).filter(([caseId]) => !managed.has(caseId)),
  );
  const persisted = persistCaseStatusOverrides({ ...preservedStatuses, ...nextSubset });
  return sanitizeCaseStatuses(persisted, managedCaseIds);
}

export function mergeCaseStatusOverrides(
  currentStatuses: Record<string, string>,
  caseIds: string[],
  status: string,
): Record<string, string> {
  const uniqueCaseIds = uniqueNonEmptyCaseIds(caseIds);
  const nextStatuses = { ...currentStatuses };

  uniqueCaseIds.forEach((caseId) => {
    nextStatuses[caseId] = status;
  });

  return sanitizeCaseStatuses(nextStatuses, [...Object.keys(currentStatuses), ...uniqueCaseIds]);
}

export function markCasesStatus(caseIds: string[], status: string): Record<string, string> {
  const currentStatuses = loadCaseStatusOverrides();
  const nextStatuses = mergeCaseStatusOverrides(currentStatuses, caseIds, status);
  return persistCaseStatusOverrides(nextStatuses);
}

export function processedCaseCount(caseIds: string[], statuses: Record<string, string>): number {
  return uniqueNonEmptyCaseIds(caseIds).filter((caseId) => statuses[caseId] === "처리완료").length;
}

function uniqueNonEmptyCaseIds(caseIds: string[]): string[] {
  return Array.from(new Set(caseIds.map((caseId) => caseId.trim()).filter(Boolean)));
}

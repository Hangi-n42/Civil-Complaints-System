export const CASE_STATUS_OPTIONS = ["미처리", "검토중", "처리완료"];

export function safeString(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return fallback;
  return String(value);
}

export function safeNumber(value: unknown, fallback = 0): number {
  const numericValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

export function readJsonFromLocalStorage<T>(
  key: string,
  options?: {
    maxBytes?: number;
    removeOnOversize?: boolean;
  },
): T | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;

    if (options?.maxBytes && raw.length > options.maxBytes) {
      if (options.removeOnOversize) {
        window.localStorage.removeItem(key);
      }
      return null;
    }

    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function sanitizeCaseStatuses(statuses: Record<string, string>, allowedCaseIds: string[]) {
  const allowed = new Set(allowedCaseIds);
  const validStatuses = new Set([...CASE_STATUS_OPTIONS, "보류"]);
  return Object.fromEntries(
    Object.entries(statuses).filter(([caseId, status]) => allowed.has(caseId) && validStatuses.has(status)),
  );
}

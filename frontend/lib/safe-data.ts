export const CASE_STATUS_OPTIONS = ["미처리", "검토중", "처리완료"] as const;

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function safeString(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return fallback;
}

export function safeNumber(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function readJsonFromLocalStorage<T>(
  storageKey: string,
  options: {
    maxBytes?: number;
    fallback?: T | null;
    removeOnOversize?: boolean;
  } = {},
): T | null {
  if (typeof window === "undefined") {
    return options.fallback ?? null;
  }

  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return options.fallback ?? null;
    }

    if (typeof options.maxBytes === "number" && raw.length > options.maxBytes) {
      if (options.removeOnOversize) {
        window.localStorage.removeItem(storageKey);
      }
      return options.fallback ?? null;
    }

    return JSON.parse(raw) as T;
  } catch {
    return options.fallback ?? null;
  }
}

export function sanitizeCaseStatuses(value: Record<string, string> | unknown, allowedCaseIdsInput: string[]): Record<string, string> {
  if (!isPlainObject(value)) {
    return {};
  }

  const allowedCaseIds = new Set(allowedCaseIdsInput);
  const allowedStatuses = new Set<string>(CASE_STATUS_OPTIONS);
  const sanitized: Record<string, string> = {};

  for (const [caseId, status] of Object.entries(value)) {
    const normalizedCaseId = safeString(caseId).trim();
    const normalizedStatus = safeString(status).trim();

    if (!normalizedCaseId || !allowedCaseIds.has(normalizedCaseId)) {
      continue;
    }

    if (!allowedStatuses.has(normalizedStatus)) {
      continue;
    }

    sanitized[normalizedCaseId] = normalizedStatus;
  }

  return sanitized;
}
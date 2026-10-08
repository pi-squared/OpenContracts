export type Finding = Record<string, unknown>;

export function isRecord(value: unknown): value is Finding {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function findingFrom(value: unknown): Finding | null {
  if (!isRecord(value)) return null;
  if (typeof value.finding === "string") return value;
  if (typeof value.state === "string" && "value" in value) return value;
  return isRecord(value.data) ? findingFrom(value.data) : null;
}

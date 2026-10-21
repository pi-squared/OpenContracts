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

export function findingOutcome(value: unknown): string | undefined {
  const finding = findingFrom(value);
  if (!finding) return undefined;
  return typeof finding.finding === "string"
    ? finding.finding
    : String(finding.state);
}

/** A presentation copy; never use this to replace retained response data. */
export function projectFindingValue<T>(value: T, suppressed = false): T {
  if (Array.isArray(value))
    return value.map((item) => projectFindingValue(item, suppressed)) as T;
  if (!isRecord(value)) return value;
  suppressed = suppressed || findingOutcome(value) === "not_found";
  return Object.fromEntries(
    Object.entries(value)
      .filter(
        ([key]) => !(suppressed && ["evidence", "evidence_quote"].includes(key))
      )
      .map(([key, item]) => [key, projectFindingValue(item, suppressed)])
  ) as T;
}

/** Merge an actual edit of the visible projection into the retained draft.
 * Absent hidden keys survive; deleting a containing object remains a deletion.
 * Array deletion paths must be supplied by the editor to retain item identity.
 */
export function reconcileFindingEdit(
  retained: unknown,
  edited: unknown,
  suppressed = false
): unknown {
  suppressed = suppressed || findingOutcome(retained) === "not_found";
  if (Array.isArray(edited))
    return edited.map((item, index) =>
      reconcileFindingEdit(
        Array.isArray(retained) ? retained[index] : undefined,
        item,
        suppressed
      )
    );
  if (!isRecord(edited)) return edited;
  const result = Object.fromEntries(
    Object.entries(edited).map(([key, item]) => [
      key,
      reconcileFindingEdit(
        isRecord(retained) ? retained[key] : undefined,
        item,
        suppressed
      ),
    ])
  );
  if (suppressed && isRecord(retained)) {
    for (const key of ["evidence", "evidence_quote"]) {
      if (key in retained) result[key] = retained[key];
    }
  }
  return result;
}

export function applyFindingJsonEdit(
  retained: unknown,
  edit: {
    updated_src: unknown;
    namespace?: (string | number | null)[];
    name?: string | number | null;
    type?: string;
  }
): unknown {
  // Align retained array entries after an explicit deletion before merging.
  let base = retained;
  if (edit.type === "delete" && edit.name != null) {
    base = structuredClone(retained);
    let parent: unknown = base;
    for (const key of edit.namespace ?? []) {
      if (key != null) {
        parent =
          typeof parent === "object" && parent !== null
            ? Reflect.get(parent, String(key))
            : undefined;
      }
    }
    if (Array.isArray(parent)) parent.splice(Number(edit.name), 1);
  }
  return reconcileFindingEdit(base, edit.updated_src);
}

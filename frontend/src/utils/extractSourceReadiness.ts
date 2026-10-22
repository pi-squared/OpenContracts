/** Refresh only an unstarted extract whose source can become ready by waiting. */
export function getSourceReadinessPollInterval(
  extract: {
    started?: string | null;
    sourceReadinessError?: string | null;
  } | null
): number {
  if (!extract || extract.started) return 0;
  const reason = extract.sourceReadinessError;
  // These are the two transient lifecycle reasons exposed by source_readiness.
  // Permanent failures require reprocessing/configuration changes, not polling.
  return reason ===
    "Document processing is incomplete. Wait for processing before extracting." ||
    reason ===
      "Document retrieval index is incomplete. Wait for indexing before extracting."
    ? 5_000
    : 0;
}

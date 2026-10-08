# Ingestion and extraction readiness

Accepted production fix: recover source-derived geometry for degenerate PDF
tokens, block extraction from unavailable sources, and keep original PDF access
available during ingestion failure. Operational diagnosis and rollout receipts
remain in private artifact storage.

## User stories

1. As a reviewer, I can process a PDF whose font reports zero advance for a glyph
   without losing its text or changing token references.
2. As a reviewer, I cannot start an extraction whose source failed processing,
   lacks complete evidence, or has no retrieval index. Queued field workers
   enforce the same readiness rule before any model request.
3. As a reviewer, I can open the original PDF from an extraction independently
   of findings. A source failure explains why extraction is unavailable and
   identifies old findings as unreliable without rewriting them.
4. As the operator, I can deploy a verified release to the existing installation,
   recover the affected source as an explicit new version, and create a linked
   replacement extraction while retaining the original run.

## Acceptance

- [ ] Recover only unambiguously matched glyph rectangles from the original PDF.
- [ ] Preserve text, page coverage, token order, and reference indexes; refresh
      enclosing annotation bounds and retain strict page-bound validation.
- [ ] Distinguish unrecoverable geometry with a safe, precise parser error.
- [ ] One shared readiness gate covers admission, orchestration, and field work.
- [ ] Failed, incomplete, or unindexed sources cause zero model invocations.
- [ ] The review grid offers Open original PDF and a clear source failure notice;
      starting extraction is disabled until all sources are ready.
- [ ] Regressions use the agreed public parser, extraction, and rendered UI
      interfaces, including currency, crop/rotation, ambiguity, and failures.
- [ ] Required frontend and staged runtime gates pass; both review axes pass.
- [ ] QA acceptance precedes production deployment; backup and rollback releases
      are retained, and the original extraction is preserved during recovery.

Domain prompts, criteria, schemas, and judgments remain owned by workflow
packages. This fix does not reinterpret existing model findings.

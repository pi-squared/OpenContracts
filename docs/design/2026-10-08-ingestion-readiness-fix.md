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

- [x] Recover only unambiguously matched glyph rectangles from the original PDF.
- [x] Preserve text, page coverage, token order, and reference indexes; refresh
      enclosing annotation bounds and retain strict page-bound validation.
- [x] Distinguish unrecoverable geometry with a safe, precise parser error.
- [x] One shared readiness gate covers admission, orchestration, and field work.
- [x] Failed, incomplete, or unindexed sources cause zero model invocations.
- [x] The review grid offers Open original PDF and a clear source failure notice;
      starting extraction is disabled until all sources are ready.
- [x] Regressions use the agreed public parser, extraction, and rendered UI
      interfaces, including currency, crop/rotation, ambiguity, and failures.
- [x] Required frontend and staged runtime gates pass; both review axes pass.
- [x] QA acceptance precedes production deployment; backup and rollback releases
      are retained, and the original extraction is preserved during recovery.

Domain prompts, criteria, schemas, and judgments remain owned by workflow
packages. This fix does not reinterpret existing model findings.

## Verification

The parser regression preserved all eight pages, 5,854 tokens and token
references, and recovered 18 currency glyphs from the original PDF. Failed,
incomplete and unindexed controls made no external model requests. Five parser
regressions, eight native readiness/schema tests, and 77 frontend tests passed;
TypeScript, the production build and staged launcher gates passed. Full-project
mypy retains its 30 existing normalized errors and adds none.

Standards and Spec reviews found no remaining implementation issues. The fixed
release passed hosted QA before publication to the existing production app.
Production recovery created source version 2 and a linked replacement extraction;
all 32 fields completed with no failures, and 60 retrieval returns contained
passages. The original extraction's source and complete findings hash remained
unchanged. Backup, rollback, native evidence and experiment receipts are retained
in approved private storage.

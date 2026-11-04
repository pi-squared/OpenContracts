# Test: Review quotation source status

## Purpose

Explain the selected finding's retained quotations and PDF associations in the
review pane, including a quotation that has several possible source locations.
The review form must preserve the saved response and comments.

## Prerequisites

- A source-bound application build with an isolated database and private media.
- A result whose effective evidence contains a uniquely located quotation and
  an ambiguous quotation. Keep original and corrected versions and comments.
- A second finding with different evidence, and a repeated quotation fixture
  whose entries have different location statuses.
- Freeze raw result and source associations before evidence API inspection;
  evidence resolvers can materialize projections. Never change live evidence.

## Steps

1. Select the exact document, extract and finding. Record their IDs and the
   effective original/corrected version. Expand its annotation group and record
   the actual source annotation IDs and page numbers.
2. Open **Edit finding**, then **Evidence**. Verify all saved quotations remain.
   A matched quotation reports its located PDF page. An ambiguous quotation
   explains that multiple source locations are possible and there is no
   highlight. Reported page and located page must remain distinguishable.
3. Close and reopen the review. Verify quotations, statuses and existing verdict
   and evidence comments persist. Cancel an unsaved comment and reopen to verify
   cancellation. On a disposable copied result, save a comment and reopen to
   verify it persisted without changing the governed response or source links.
4. Close the review and inspect a different finding. Verify it shows its own
   quotations, statuses and comments, without inheriting the first finding.
5. Use repeated quotations with different source statuses. Verify their actual
   field/index associations determine the status. A stale projection with a
   different quote, reported page or selection path must report unavailable
   location rather than borrowing another quotation's location.

For a synthetic example, a result quotes `Rate label` and `%` on page3. The label
has one retained match, while the percent quotation has several possible source
locations and no highlight. Explain that difference without inventing coordinates
or dropping either quotation. Preserve the original response and review history.
Authorized exact-case reproduction details belong in the
[private issue](https://github.com/pi-squared/OpenContracts-Development/issues/42)
and private execution receipts.

## Automated regression

Run `src/components/annotator/sidebar/__tests__/ReviewEvidence.test.tsx` with the
frontend Vitest toolchain and run `tsc --noEmit`. The regression exercises the
real results component, editor, review form and quotation list with selected
finding projections; the analysis context is controlled. Source-bound full-app
recordings remain necessary to establish actual selection and PDF integration.

## Cleanup

Close owned tabs and retain private before/after fingerprints, sanitized result
identity, source/build manifests and finalized video receipts. Remove only the
authorized disposable resources. Do not commit raw contract data or recordings.

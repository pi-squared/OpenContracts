# Original quotation source binding

Use an isolated local database copy. Do not edit the source PDF, quotations,
legacy associations or saved original/corrected findings. No extraction,
ingestion, retry or model call is required.

Use a synthetic finding with two retained original quotations: a matched
`Rate label` on physical PDF page 3 and an ambiguous `%` on that page. A retained
historical domain association for `%` points to an unrelated document heading.
The stored original quote still has `status: ambiguous` and no located page.
The private issue records the exact runtime reproduction; public fixtures use
neutral values: <https://github.com/pi-squared/OpenContracts-Development/issues/42>.

1. Open the original finding using its normal original-value source link.
2. Inspect the original-version `findingEvidence` response. Both quotations
   remain present. The matched quotation retains its located source; the
   ambiguous quotation has no annotation ID or IDs and retains its ambiguous
   status, reported page and absent located page.
3. Inspect `fullSourceList(version: "original")` and the source cards. Only
   located quotations supply selected highlights. The unrelated document
   heading does not appear as a selected source for the ambiguous quotation.
4. Open the matched source. Confirm the actual PDF paints, the expected source
   card and highlight become active, and their positions match the stored
   source coordinates. The historical cache ID may be projected to its exact
   retained original domain annotation; do not assume both IDs must be equal.
5. Return to the effective/corrected finding, then inspect another finding.
   Confirm their own source cards, quotations and comments remain separate.
6. Compare raw scoped database snapshots before and after browsing. Original
   and corrected values, reviewer comments/decisions, cached quotations,
   historical association rows and annotation metadata must remain unchanged.

Record a source-bound native WebM and private raw API/state receipts for the
current application head. Unit tests alone do not establish actual-PDF
acceptance. Preserve prior failing recordings and their original hashes.

The focused `test_original_evidence_projection` suite uses `SimpleTestCase` and
mocked annotation reads. It checks the original ambiguous shape, stale cached
IDs, matched/different-page originals, exact cell/version/fingerprint binding,
original source-list eligibility, effective mode and no-evidence findings.

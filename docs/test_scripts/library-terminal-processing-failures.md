# Test: Terminal processing failures in the document library

## Purpose

Verify truthful failure display and consistent library filters/counts without
retrying failed processing or changing stored document history.

## Prerequisites

Use an isolated test environment with a terminal failed document, an actively
processing document, and a successfully processed document. Include failed rows
with retained and released backend locks. Retain the actual failure cause; a
filename alone does not establish invalid file content.

## Steps

1. Open Documents and find each fixture in Grid, List and Compact views.
2. Confirm failed rows show **Processing failed** and a useful next step. A
   missing processing component should ask the reader to contact an administrator.
   Raw backend paths and tracebacks should not appear.
3. Select Processing and Processed. Neither should contain failed rows, regardless
   of their lock flag. All Documents should still contain them.
4. Compare both status counters with the full permission-filtered result set.
   Failed rows count toward total documents/pages, but neither status counter.
5. Confirm genuine processing rows retain their progress presentation, completed
   rows remain processed, and legacy rows retain their lock-based behavior.
6. Reopen/reload and confirm the same statuses without retry or upload actions.
7. Check List at widths of 600, 768, 769 and 1024 pixels. At narrow widths the failure
   and next step should remain visible on a second row without horizontal overflow.

## Expected results

All three views, filters and server aggregates agree. Existing document data,
processing causes, review feedback and access permissions remain unchanged.

## Cleanup

Close test sessions. Keep fixtures and recorded acceptance evidence in their
designated private test store; do not place source files in this repository.

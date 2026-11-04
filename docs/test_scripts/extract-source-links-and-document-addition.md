# Test: Extract source links and document addition

## Purpose

Verify source navigation respects the router basename and that selecting already
processed documents refreshes extraction readiness and original-PDF metadata.
The source mapping is `SourceReadinessNotice::OriginalPdfLink`; document-addition
handlers live in `ExtractDetail` and the shared `ExtractDetailContent`.

## Prerequisites

- An isolated full application, database and media store at the selected source
  revision; never modify shared documents or existing human review data.
- Builds served at `/opencontracts/` and `/impeccable/`, with real local APIs.
- Four synthetic PDFs whose processing and indexes have already completed, and
  a fieldset containing one extraction column.
- A source-bound native browser recording at the current build identity.

No extraction or ingestion provider call is needed for these source-selection
checks. Do not start paid work without the experiment's recording and admission
controls.

## Steps

1. Under `/opencontracts/`, create a new extract with the fieldset and no corpus.
   Confirm that no documents are selected, the source warning is present and
   **Start Extract** is disabled.
2. Use **Add documents** to select one already processed synthetic PDF. Confirm
   that its row appears, **Start Extract** becomes enabled without Refresh and
   the false source warning disappears.
3. Inspect **Open original PDF** in the Data grid and equivalent Documents-tab
   links. Its `href` must retain `/opencontracts/` and target the actual document.
4. Click the link normally. Verify that a new tab loads the actual PDF canvas,
   rather than accepting only an HTTP-success or page-shell response. Repeat
   using the platform's modifier-assisted new-tab action.
5. Create another corpus-free extract and add four processed PDFs together.
   Confirm all four original-PDF links and immediate readiness, without Refresh.
6. Repeat the navigation and one/four-document selection checks under
   `/impeccable/`. Repeat through the embedded corpus extract view where that
   view is in scope.
7. Verify the negative controls: an empty extract remains blocked, a server
   response reporting a genuine source problem stays blocked after addition,
   and a rejected document-addition mutation does not show a successful change.

## Expected results

The extract query is the authority for source metadata and derived readiness.
Successful additions refresh that query rather than appending partial mutation
objects. PDF links honor the active router basename, retain native new-tab
behavior and do not trigger the containing row's selection action.

## Automated regressions

Run the focused Vitest tests with the repository frontend toolchain:

```sh
vitest run src/components/extracts/__tests__/OriginalPdfLink.test.tsx \
  src/views/__tests__/ExtractDocumentAddition.test.tsx \
  src/views/__tests__/ExtractSourceReadiness.test.tsx
tsc --noEmit
```

The tests retain the actual views, Data grid and Apollo query/mutation lifecycle.
The document picker supplies synthetic selected IDs; full application recordings
remain required to establish actual PDF rendering and integration behavior.

## Cleanup

Close owned browser tabs and servers. Remove only the isolated test extracts and
fixtures through the approved test-resource cleanup. Retain source/build IDs,
finalized WebM hashes and passing/failing receipts in the private execution
record; do not commit private runtime state or recordings.

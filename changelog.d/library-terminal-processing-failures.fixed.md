The document library now displays terminal processing failures in grid, list and
compact views with an actionable message. Failed documents no longer appear in
the Processing or Processed filters and counters when a backend lock is retained.
The slim document query fetches status/error fields; existing active and legacy
lock behavior is preserved. See `frontend/src/utils/documentProcessing.ts` and
`config/graphql/document_queries.py::_resolve_Query_document_stats`.
Narrow List layouts retain the failure message on a second row instead of hiding
it with the ordinary status column.

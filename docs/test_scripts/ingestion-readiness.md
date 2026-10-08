# Ingestion readiness acceptance

Purpose: verify source-derived glyph recovery and extraction admission on the
independent QA installation before updating an existing production installation.

Prerequisites: a verified prepared recipe, locked runtime and browser dependencies,
an explicitly selected Databricks CLI profile, and the public currency regression
PDF with SHA-256 recorded by `test_source_geometry.py`. Keep operational evidence
and model responses in approved private storage.

1. Run the source geometry controls with `WARP_CURRENCY_SOURCE` pointing to the
   unchanged PDF and `WARP_RUNTIME_ROOT` to its verified parser assets. Expect
   eight pages, 5,854 tokens, 18 recovered rectangles, and unchanged text/indexes.
2. Run `test_extraction_readiness.py` with `OPENCONTRACTS_QA_CONTEXT` selecting the
   independent QA installation and the prepared fixed source. Expect admission,
   orchestration and queued fields to reject unavailable sources with zero
   provider requests. Complete indexed sources must pass the same rule.
3. Run the complete maintained frontend suite, TypeScript and production build,
   then stage the release and pass the staged runtime gate.
4. Deploy to QA. Upload the currency PDF and wait for complete parsing and indexing.
   Verify original PDF rendering and run a native extraction against the installed
   workflow. A located quotation must open its PDF evidence.
5. Inspect an unavailable-source extraction: expect the source failure notice,
   disabled extraction start, original PDF access, and retained old findings.
6. Retain the production database backup and rollback release, deploy the tested
   source, and import a fresh explicit document version. Start a linked replacement
   extraction only after readiness succeeds. Verify the old extraction is retained.

Cleanup: remove only this control suite's synthetic rows. Retain uploaded source
versions, replacement extractions, release identities and private acceptance
receipts. Never reset an installation or overwrite the failed run.

# Ingestion readiness acceptance

## Purpose

Verify original glyph recovery, extraction readiness, and PDF access in QA before
updating an existing production installation.

## Prerequisites

Use a verified prepared recipe, locked Python/Node/browser dependencies, an
explicitly selected Databricks CLI profile, and the unchanged public currency
PDF identified by `test_source_geometry.py`. Set `QA_CONTEXT` to a private Python
bootstrap which verifies the independent QA project before configuring Django.
Set `RUNTIME_PYTHON`, `PREPARED`, `NODE_BIN`, `PDF_SOURCE`, `WARP_ASSETS`, and
`PRIVATE_ARTIFACTS` to absolute local paths. Keep operational evidence private.

## Steps

1. Run the configured parser and native regressions:

   ```bash
   WARP_CURRENCY_SOURCE="$PDF_SOURCE" WARP_RUNTIME_ROOT="$WARP_ASSETS" \
     "$RUNTIME_PYTHON" -m unittest discover -s databricks/tests -p test_source_geometry.py
   OPENCONTRACTS_QA_CONTEXT="$QA_CONTEXT" \
     "$RUNTIME_PYTHON" -m unittest discover -s databricks/tests -p test_extraction_readiness.py
   python databricks/tools/test_frontend.py --upstream "$PREPARED" \
     --node-bin "$NODE_BIN" --build --report "$PRIVATE_ARTIFACTS/frontend.json"
   ```

2. Stage for the existing QA origin and workflow volume. Set `RELEASE`, `QA_ORIGIN`,
   `WORKFLOW_ROOT`, `WARP_WHEEL` and `RAPIDOCR_WHEEL` from its verified installation:

   ```bash
   python databricks/tools/stage_app.py --upstream "$PREPARED" \
     --destination "$RELEASE" --app-origin "$QA_ORIGIN" \
     --workflow-package-root "$WORKFLOW_ROOT" --warp-wheel "$WARP_WHEEL" \
     --rapidocr-wheel "$RAPIDOCR_WHEEL" --warp-nltk-data "$WARP_ASSETS/nltk-data"
   "$RUNTIME_PYTHON" databricks/tools/verify_staged_runtime.py \
     --release "$RELEASE" --python "$RUNTIME_PYTHON" --output "$PRIVATE_ARTIFACTS/gate.json"
   ```

3. Deploy through `databricks/tools/deploy_installation.py publish` using the
   existing QA installation journal, selected CLI/profile, release and gate receipt.
   Upload the currency PDF through the native app, wait for complete processing
   and indexing, then run the installed native workflow. Open a located quotation
   in its PDF. Record browser evidence privately.
4. Inspect an unavailable-source extraction. Check its failure notice, disabled
   start action, original PDF link and retained findings.
5. Retain the production schema backup and previous gated release. Deploy to the
   existing production installation, import a new explicit source version, wait
   for readiness, and create a linked replacement extraction.

## Expected Results

The original PDF yields eight pages, 5,854 tokens and 18 source-derived repairs
with unchanged text and reference indexes. Ambiguous and out-of-page locations
fail. Unavailable sources cause zero model requests at admission, orchestration
and field workers. All frontend tests, TypeScript/build and staged runtime checks
pass. Original PDFs remain accessible independently of evidence; located quotes
open the correct page. Production source versions and the original run remain
available alongside the linked replacement.

## Cleanup

The regression suite removes only its synthetic rows. Retain uploaded versions,
replacement extractions, rollback release and private acceptance receipts. Never
reset an installation or overwrite the original findings.

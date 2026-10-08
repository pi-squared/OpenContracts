# Fresh Docling jobs and independent corpus

The owner authorized wiring the Fresh app to parse PDFs with Docling on
Databricks jobs and creating a separate corpus from all 29 entries in
`2026-tnc`: 28 PDFs and the README. Preserve the original corpus, original
source bytes, structural evidence, findings and review state. Report parser
failures truthfully. This is implementation and processing authorization,
including deployment to `oc-fresh-261008` through the existing service principal.

Fresh's deployed baseline is the fork recipe at
`e0815e6921554a2dc7abc5f0dbaa6ed88be57528`; retain its ingestion and readiness
fixes. Keep Warp as the normal PDF default. Register a selectable native Docling
job parser, with the job and private artifact volume supplied by resource
bindings. Run Docling-slim 2.132.0 on serverless with the verified headless
OpenCV dependency and a separate child process. Record source hashes, parser
options, dependency/environment identity, job/run identity, timings and output
hashes. Model-asset revisions without evidence remain unknown.

The app's managed identity submits and monitors jobs, checks immutable result
identity and imports the resulting text and original-PDF geometry through the
native parser persistence and indexing paths. Each source has a durable attempt
and idempotency token before submission. Recovery reuses that job attempt; it
must not silently repeat parser work or attach late output to another source.
Use fresh document records with independent structural annotation sets in the
copy; identical original bytes must not reuse or overwrite Warp evidence.

Name the new corpus `2026-tnc-docling`. Its creation and progress interface must
be authenticated, return promptly, preserve failed records, and permit status
inspection and bounded recovery. Copy the README as a text entry. Do not run
Terms assessments or copy existing findings into this parser corpus.

Verification covers the existing native parser persistence interface, the
authenticated corpus-copy/status interface, and deployment resource bindings.
Exercise successful, failed, duplicate and interrupted job outcomes with
independent source/hash expectations. Run the required staged parser/launcher
gate and hosted checks, verify the 28 PDF results and README, original-byte
hashes and native readiness/embeddings, and compare the original corpus's saved
state before and after. Review Standards and Spec against the fixed baseline.

Related verification experiment: OpenContracts-Databricks issue 115. Its
32-field assessment and side-by-side domain comparison remain separate from
this requested parser integration and corpus creation. Operator processing and
verification use the shared ExperimentRunner/HistoryStore; hosted-app MLflow
synchronization remains deferred.

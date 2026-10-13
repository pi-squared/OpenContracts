# OpenContracts on Databricks

This fork keeps stock OpenContracts intact and maintains the Databricks recipe
in this directory. The recipe pins the fork's stock commit, declares additions,
and applies hash-verified patches in order. Patches 0001–0014 reproduce
live port release 0015. Patches 0015–0016 add automatic quotation repair with
experiment 95's retained-word mechanism and ordinary quotation rendering.
Patch 0017 regenerates the GraphQL contract for the served port API. Evidence
persistence resides in native extraction/annotation services; compatibility
imports retain the existing port entrypoints. Patch 0018 defers the empty personal
corpus to the first upload.

The app uses a new Lakebase project, configurable model endpoints and the native
OpenContracts workflows. Startup creates its schema, runs migrations and creates
the uncapped shared pilot owner. It can install configured definition packages;
it imports no documents, corpora, extracts or saved results.

## Build and deploy

For development-to-testing promotion, existing Lakebase, bound workflow packages
and direct deployment from the canonical Git testing branch, follow the
[testing promotion workflow](docs/testing-promotion.md). It extends these same
controllers and preserves the fresh provisioning/snapshot mode below.

Use Git, Python 3.11, uv, Node 22.16 or later, Corepack/Yarn and Databricks CLI 1.0 or
later. Select a workspace profile explicitly. Keep authentication configuration,
build artifacts, deployment journals and logs outside this repository.

Provision a named installation first:

```bash
python databricks/tools/deploy_installation.py \
  --cli /absolute/databricks --profile SELECTED_PROFILE \
  --installation example --state-directory /absolute/private/example \
  provision --extraction-endpoint databricks-gpt-oss-120b \
  --embedding-endpoint databricks-gte-large-en \
  --grounding-endpoint databricks-gpt-oss-120b \
  --definition-volume catalog.schema.definitions
```

The bundle creates `oc-example`, creates a Lakebase project with the same name,
and attaches its production database to the App. The App identity receives
database creation/connect permission, model query permission and read access to
the definition volume. Deployment state and releases live in the provisioning
principal's workspace folder. Provisioning leaves the App stopped until a gated
release is published.

An installation name and its private journal identify one App/Lakebase pair.
Repeat provisioning resumes or updates that pair and preserves its contents.
A different name and new journal create a fresh pair. Unknown name collisions,
changed ownership markers and missing previously provisioned resources fail.
Keep the journal with private recovery artifacts; the command has no adoption,
reset or deletion operation.

Build using the generated App URL from `installation.json`:

```bash
python databricks/tools/build_release.py \
  --work-directory /absolute/private/new-build \
  --app-origin https://GENERATED_APP_HOST \
  --node-bin /absolute/node/bin --runtime-python /absolute/runtime-venv/bin/python \
  --warp-wheel /absolute/warp_ingest-2.1.0-py3-none-any.whl \
  --rapidocr-wheel /absolute/rapidocr_onnxruntime-1.4.4-py3-none-any.whl \
  --warp-nltk-data /absolute/verified-nltk-data \
  --workflow-package-root /Volumes/catalog/schema/definitions/workflow-packages
```

The build fetches the pinned stock commit from this fork by default, checks
licenses and protected stock files, applies additions and patches, installs the
frozen frontend lock, runs frontend checks and builds production assets. Staging
packages application code and assets and builds the separately pinned Warp
dependency. Tests, fixtures, cassettes, operator tools, PDFs and tabular/database
artifacts are excluded. The runtime gate requires the exact staged parser and
launcher control to execute successfully with zero skips.

Omit `--runtime-python` to have the build create an isolated environment from
the release's `requirements.txt`, including its two local vendor wheels. An
explicit runtime interpreter must already contain those dependencies. For separate
build/stage/verification steps, use `prepare_upstream.py`, `test_frontend.py`,
`stage_app.py` and `verify_staged_runtime.py`; the gate also accepts a successful
receipt for adjacent revalidation.

Publish a verified release:

```bash
python databricks/tools/deploy_installation.py \
  --cli /absolute/databricks --profile SELECTED_PROFILE \
  --installation example --state-directory /absolute/private/example \
  publish --release /absolute/private/new-build/release \
  --receipt /absolute/private/new-build/runtime-gate.json \
  --python /absolute/runtime-venv/bin/python
```

Publication checks the App identity and origin, revalidates the staged gate,
uploads an inventory-addressed release, exports it to compare every byte, then
deploys a Databricks snapshot. Deployment receipts stay in the private journal.
Never use `bundle destroy`: the bundle protects its Lakebase project from
destruction, and data recovery requires an explicit operator procedure.

## Definitions and grounding

The separate [definition installer](https://github.com/pi-squared/OpenContracts-Databricks/blob/feature/fresh-port-definition-installer/tools/install_opencontracts_definitions.py)
lives in `OpenContracts-Databricks`, outside this deployed fork. Its
[operator guide](https://github.com/pi-squared/OpenContracts-Databricks/blob/feature/fresh-port-definition-installer/docs/design/2026-10-08-fresh-port-definition-operator.md)
provides a complete invocation. It
uploads only manifest-declared, hash-verified definitions to the attached volume,
configures `WORKFLOW_INSTALL_HASHES`, runs the release gate and publishes through
this controller. `--configure-only` prepares configuration without claiming the
backend has installed it. The application loader preserves nested Pydantic
models and validators and creates native Fieldsets, Columns and LabelSets. Repeat
loading checks the same native IDs and exact definitions; edited definitions
require a new package revision. It never creates a corpus or analysis binding.

Machine grounding runs after a successful field. Exact matches are retained;
unresolved quotations receive one recorded repair attempt each. The mechanism
ranks same-document fine passages with word/word-pair TF-IDF, supplies the top
five to the configured model, and independently locates returned quotations in
retained PDF words. Separate excerpts and physical pages remain separate. A
failed, ambiguous or interrupted attempt leaves the finding unresolved. Reads
reuse saved responses without inference. Requests, settings and responses stay
in Lakebase; no OAuth headers are recorded.

Machine repair never changes `data` or `corrected_data`. Genuine reviewer edits
take precedence and use exact matching only. Superseded highlights are hidden
while source history remains retained. Generic quotation labels work without a
domain policy; approved package policies bind when the user selects the matching
installed Fieldset/LabelSet for a corpus.

Repair settings are `GROUNDING_ENABLED`, `GROUNDING_MODEL_ENDPOINT`,
`GROUNDING_REASONING_EFFORT`, `GROUNDING_TEMPERATURE` and
`GROUNDING_MAX_TOKENS`; defaults reproduce experiment 95's GPT-OSS-120B settings
of low reasoning, temperature zero and 4096 output tokens. Endpoint names and
embedding dimensions remain configurable. Native processing runs in a bounded in-process Celery worker so browser requests
return promptly. The memory queue does not survive App restarts; a durable
asynchronous queue remains outside this release.

`/port/installation-status` provides aggregate counts and parser/usage-cap
checks behind the Databricks App boundary. Use an independent QA installation
for upload, extraction and PDF viewing. Delivery should have zero documents,
corpora, extracts and datacells after definitions are installed.

## Verification

```bash
cd databricks
python -m unittest tests.test_quote_repair tests.test_finding_evidence \
  tests.test_workflow_packages tests.test_stage_app \
  tests.test_build_warp_runtime tests.test_installation_lifecycle
python -m unittest tests.test_databricks_transport tests.test_browser_token_transport
```

Transport checks need local loopback sockets. Frontend checks need a verified
prepared checkout and the frozen dependencies. Real parser/launcher checks need
the staged vendor dependencies and declared assets. Deployment acceptance is
recorded separately from these synthetic checks.

Hosted acceptance is recorded in the [fresh installation receipt](../docs/verification/2026-10-08-fresh-databricks-installation.md).

## Docling PDF jobs

The optional native parser `Docling · Databricks Job` runs Docling-slim 2.132.0
on a separate serverless job. Build or stage with `--docling-jobs` and bind a job
as `docling-job`, plus an artifact volume as `docling-artifacts` (WRITE_VOLUME)
and `docling-artifacts-read` (READ_VOLUME). The job binding requires
CAN_MANAGE_RUN. Keep Warp as the normal PDF default; select the native Docling
parser for an ingestion run, or use the authenticated corpus-copy interface.

Create the job settings with `tools/docling_job_config.py:job_settings`, supplying
the App name, an immutable workspace directory containing
`jobs/docling_pdf_job.py` and `port/python/databricks_port/parser_exports.py`, the
authorized run-as principal and a volume URI for the OCR wheel. Build that wheel
with `tools/build_docling_ocr.py:build` from the hash-pinned stock RapidOCR wheel.
The builder changes only distribution metadata to require headless OpenCV; all
OCR code and model bytes remain identical. Keep these dependencies in the job
environment. Add `docling_job_id`, `docling_artifact_volume` and
`docling_job_revision` to the private installation journal so later bundle
operations preserve the bindings. Validate the bundle and publish through the
existing gated installation controller.

`POST /port/docling/corpora` accepts `source_corpus_id` and `title`, copies PDF
sources and a text README into separate native records, and returns immediately.
`GET /port/docling/corpora/<id>` returns progress. Repeating creation recognizes
the copied source provenance. `POST /port/docling/corpora/<id>` resumes an
interrupted native processing chain using its retained attempt. It requires
update permission on the corpus and every document, skips completed sources and
never silently reruns a failed remote parse. Active chains in the current App
process are not queued twice. The native JWT is required in addition to the
Databricks App boundary.

Receipts retain source/output hashes, exact pipeline options, packages, worker
identity and timings. Cached model snapshots are an inventory; actual model
revisions remain unknown without evidence. Paragraph and table boxes retain
original PDF coordinates. Docling evidence is imported through native parser
persistence and indexing, with separate structural sets from Warp evidence.

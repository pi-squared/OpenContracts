# Fresh Databricks installation acceptance

The canonical port recipe is on `pi-squared/OpenContracts`, branch
`feature/databricks-patched-port`. It assembles stock commit
`1e859dcea0f083f374c160a04244f93bca5b989c` from that fork, applies 18 ordered
hash-verified patches and 32 declared additions, and verifies protected stock
files and final target hashes. Patches 0001–0014 reproduce live release 0015;
the additions retain experiment 95's quotation repair without its presentation
workarounds. Stock application source in this branch remains intact; assembly
applies the maintained recipe to a separate checkout.

## Delivery

The new app is [oc-fresh-261008](https://oc-fresh-261008-7405605345306464.4.azure.databricksapps.com).
Its own Lakebase project is `oc-fresh-261008`. The independent QA app and project
are `oc-qa-261008`. Existing live resources and document state were retained.
The explicitly selected `EXPERIMENT_SP` provisions resources; each App uses its
own generated identity for its attached database, model endpoints and package
volume. Journals, connection information, operational logs, requests, responses
and screenshots remain in private artifact storage.

Final delivery has zero documents, corpora, extracts and datacells, two Fieldsets
and two LabelSets. The shared owner is uncapped and the default PDF parser is
`WarpLocalParser`. It contains only these versioned definitions:

| Package | Version | Columns | Labels |
| --- | --- | ---: | ---: |
| Terms | `3.0.0-20261005` | 32 | 38 |
| FSPO | `fspo-column-v3` | 17 | 28 |

Manifest hashes are recorded in the accepted design. All 49 nested response
models resolve through verified packages. The separate operator command uploads
only declared definition files and invokes the deployment-controlled backend
loader after migrations. The full operator publication path ran successfully;
repeat loading retained native IDs. Native edits are rejected rather than
silently replaced. Delivery has no workflow corpus or automatic-analysis binding.

The first stock owner startup created an empty personal corpus. Patch 0018 now
defers that creation until first upload. The only empty placeholder in the new
delivery database was reconciled after checking that no documents or results
existed. Native user actions can subsequently create their own corpora.

## Native QA

QA used two public source PDFs in its own database. No QA document, result,
extraction, screenshot or database export entered delivery or the deployed
archive. Native API operations loaded the installed definitions, created QA
corpora, uploaded PDFs and started the fieldsets.

| Workflow | Physical pages | Native fields | Completed | Failed |
| --- | ---: | ---: | ---: | ---: |
| FSPO, `2020-0299.pdf` | 15 | 17 | 16 | 1 |
| Terms, BMW hire purchase | 22 | 32 | 32 | 0 |

The FSPO failure remains a native failed cell; no answer was fabricated or
replaced. These counts verify processing behavior, not semantic assessment
quality. The model endpoints were `databricks-gpt-oss-120b` for extraction/repair
and `databricks-gte-large-en` for embedding. Repair used low reasoning,
temperature zero and 4096 output tokens.

The original eager FSPO request exceeded the gateway timeout. Its saved run
finished and was audited without repeating inference. Native tasks now run in a
bounded in-process Celery worker; the subsequent Terms start request returned
in 0.425 seconds. Its memory queue does not survive an App restart. Durable task
dispatch and hosted per-model MLflow synchronization remain deferred.

There were 33 retained quotation repair responses, each with one admitted
invocation. Independent checks verified all 65 distinct displayed quotation
annotations against retained PDF token identities, physical pages and geometry.
Repairs require exact word bounds; deterministic matches retain PlasmaPDF's
native padding. All observed quotations had a located source. Original machine
values remained separate from repair evidence, and no native cell had a human
correction introduced by repair.

Chromium opened a native finding, followed its quotation into the original PDF
and rendered four PDF canvases, with zero page or App HTTP errors. Ordinary
quotation highlights appeared without changed-highlight notices or a machine
View Original control. The test browser seeded an ephemeral local cookie
preference; it submitted no native consent mutation.

Six controls against QA Lakebase passed: repeated reads with one invocation and
original highlight restoration; interrupted admission without repeat;
saved-response projection recovery without inference; a separate database
connection committing a human correction before a late response; definition ID
preservation and refusal of native edits; and owner freshness. Annotation
embedding dispatch was mocked only in these ORM controls. Actual hosted parsing,
embedding, extraction and repair ran through the App. ExperimentRunner retained
QA requests, settings, responses, outcomes and private artifacts in the shared
local history store.

## Build and review

A clean invocation of `build_release.py` fetched the fork, applied the recipe,
installed the frozen frontend lock, ran 76 frontend checks, compiled TypeScript,
built production assets, created an isolated runtime with 234 pinned packages,
and passed the required staged parser/launcher gate. Subsequent startup/worker
changes were reassembled and gated; frontend inputs were byte-identical and its
verified assets were reused. Both final staged releases executed the required
parser/launcher control with zero skips. Publication exported uploaded bytes
and compared the complete release inventory before snapshot deployment.

Focused parser packaging, source evidence, workflow package and installation
controls passed, as did 12 transport/browser-token controls, four standalone
installer tests, the native GraphQL schema parity check and a real asynchronous
Celery worker control. All affected pre-commit hooks passed. Black ran separately
per file after its process pool stalled in this environment.

The two review axes were kept separate. Initial Standards findings concerning
SDL parity, service-layer ORM ownership and duplicate volume validation were
resolved. Follow-up review identified stale eager-processing ADR wording; this
receipt accompanies its correction. Spec review found no new code defect. Hosted
acceptance above closes its earlier processing/viewer and durability evidence
requirements. The failed FSPO field and memory queue limit remain explicit.

## Reuse

Follow [the recipe](../../databricks/README.md) to provision a named App/Lakebase,
build from the pinned fork, configure definitions and publish a gated snapshot.
A new installation name and private journal create fresh resources. Repeating a
known name preserves its resources and state; unknown collisions fail.

The definition installer is maintained separately in
[OpenContracts-Databricks](https://github.com/pi-squared/OpenContracts-Databricks/blob/feature/fresh-port-definition-installer/tools/install_opencontracts_definitions.py).
Its [operator guide](https://github.com/pi-squared/OpenContracts-Databricks/blob/feature/fresh-port-definition-installer/docs/design/2026-10-08-fresh-port-definition-operator.md)
provides the complete invocation. The deployment archive excludes operator
scripts, tests, fixtures, cassettes, PDFs and tabular/database artifacts.

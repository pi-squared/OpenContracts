# Fresh Databricks port design interview

Status: accepted. The owner confirmed Q1–Q8; implementation and deployment are authorized.

## Agreed scope

The owner requested a new branch/worktree in `pi-squared/OpenContracts`, a
reusable deployment process that creates and attaches new Lakebase, and a fresh
app matching live release 0015 plus experiment 95's grounding mechanism.
Existing documents, PDFs, extracts, results and processed artifacts must not be
imported. Repaired evidence must appear normally, without experiment notices,
changed-highlight decorations or original-value controls caused by repair.

The separate definition command must load through the application backend and
live outside the deployed repository. Existing versioned Fieldset schemas,
including nested models and validators, and LabelSet definitions live in a
Databricks volume. GraphQL is not required for installation. The installer must
verify versions, prevent duplicates and reject silently overwriting edits; it
must not use a database dump or copy assessment state. The owner expressly
authorized the sole existing Databricks service principal for provisioning.

Delivery installs only Fieldsets and LabelSets and creates no workflow corpora,
automatic-analysis bindings, documents or extracts. A repair failure retains
the finding with a plain unresolved-source state. A separate temporary QA
environment verifies upload, assessment, grounding and PDF inspection; its
documents and results never enter the delivered app or Lakebase.

## Settled repository setup

- Worktree: `.worktrees/opencontracts-fork-port` in DocumentAnalysis.
- Branch: `feature/databricks-patched-port`, rooted at the fork's stock main
  commit `1e859dcea0f083f374c160a04244f93bca5b989c`.
- Canonical origin: `https://github.com/pi-squared/OpenContracts.git`.
- Keep the maintained recipe in `databricks/`; assembly fetches the exact stock
  commit from this fork and applies the declared additions and ordered patches.
- This worktree was seeded from the existing local Git object. No dirty prepared
  files, business data or experimental outputs were copied. The fork pin was fetched and the declared recipe transferred without importing
  documents, results or experimental publication artifacts.

## Facts shaping the design

The fork is an upstream fork and its main is the existing upstream pin. Current
port modules, patches and lock match release 0015; newer staging tools add the
required isolated archive/parser/launcher gate. The archive's existing fixtures
namespace contains benchmark text and recorded model cassettes and must be
excluded for this fresh release. Startup currently migrates and creates its
owner identity without importing documents or domain definitions.

Native GraphQL can create Fieldsets, Columns, LabelSets and labels. It cannot
transfer the owner's full nested Pydantic schemas and validators as ordinary
native text definitions. Existing `workflow:<hash>:<key>` types resolve trusted
packages from the configured read-only package root without ORM registration.
Native mutations also omit column display ordering and approved package label
policy binding. Q1 settles these installation limitations through a backend
loader adapted from `tools/install_workflow_package.py`, rather than new GraphQL
installation mutations. A deployment-controlled loader inside the app may run
after migrations using its own identity. Q2 authorizes definition installation
during delivery, without corpus setup or automatic-analysis bindings.

Experiment 95 ranks same-document fine passages with word/word-pair TF-IDF,
asks a Databricks model to select quotation text from the top five, then locates
that text independently against retained PDF words. Its experimental publication
uses parent extract copies and `corrected_data`, which causes the original-value
button. Production repair should retain separate machine grounding results and
reserve corrected findings for actual reviewer edits. Separate excerpts/pages
and ordinary evidence labeling need integration through the native renderer.

## Design tree

1. **Fresh installation and fork ownership — settled by the owner's request.**
   - Repository layout and pinned assembly — routine choice delegated to agent.
   - Reusable provisioning, instance identity and repeat deployment — Q7.
   - Fresh owner's usage limits for live parity — Q8.
2. **Definition installation — Q1/Q2 settled.**
   - Schema transport — volume-backed versioned packages and a simple backend
     loading command; retain nested models, validators and label definitions.
   - Preserve version checks; prevent duplicates and silent overwrite of edits.
   - Install Fieldsets and LabelSets only; verify an empty document/result state.
3. **Grounding mechanism and ordinary presentation — scope settled.**
   - Failure policy — Q3 settled: retain finding with plain unresolved source.
   - Repair timing, human quotation precedence and correction presentation — Q5.
   - Repair endpoint/configuration — Q6.
4. **Verification isolation — Q4 settled.**
   - Use a separate temporary QA environment for full-path acceptance.
   - Keep delivered app and its Lakebase free of QA documents and results.
5. **Workspace access — Q6 confirmed and verified.**
   - Project-local Databricks CLI 1.19.0 is verified and selected explicitly.
   - The existing private OAuth M2M config's `EXPERIMENT_SP` profile was validated
     against the existing live workspace. No credentials enter this fork.
   - The authorized principal provisions resources; Databricks creates a managed
     runtime identity for each new App.

## Round 1 — complete

| Question | Recommendation | Alternative |
| --- | --- | --- |
| Q1: how to preserve nested schemas and validators? | **Confirmed:** keep existing versioned schemas and LabelSets in a Databricks volume; provide a simple backend loading command, preserving validation/version checks and preventing duplicates or silent overwrites. | Native GraphQL installation is not needed; no new portable schema format. |
| Q2: what should the separate installer do on delivery? | **Confirmed:** install fieldsets and LabelSets only. | No corpus setup or automatic-analysis bindings. |
| Q3: what happens when repair cannot locate evidence? | **Confirmed:** retain the finding with a plain unresolved-source state. | Do not fail the complete field or invent a highlight. |
| Q4: how to verify processing while delivering a fresh installation? | **Confirmed:** use a separate temporary QA environment. | QA data never enters the delivered app or its new Lakebase. |

The owner confirmed Q1 in a side conversation and requested forwarding that
decision to this interview. Q1 does not settle initial configuration, grounding
failure policy or QA isolation by itself; the owner subsequently confirmed
Q2–Q4 in the main conversation. See the
[definition-loading ADR](../adr/0002-load-versioned-definitions-through-backend.md)
and [unresolved-evidence ADR](../adr/0003-retain-findings-with-unresolved-evidence.md).

## Round 2 — complete

| Question | Recommendation | Alternative |
| --- | --- | --- |
| Q5: when does repair run and which review controls remain? | **Confirmed:** automatic repair after each successful machine field, once per unresolved quote; exact matching only for human edits; human corrections take precedence. Machine repair creates no experiment decorations or original-value action. Keep normal controls for genuine human corrections. | Hide every original-value control, or run repair only by an explicit command. |
| Q6: which workspace/profile and models? | **Confirmed:** select discovered `EXPERIMENT_SP` for the existing live workspace, reuse its extraction/embedding endpoints, and select Databricks GPT-OSS-120B for configurable repair with experiment 95 settings. | Choose different deployment settings. |
| Q7: what does repeat deployment mean? | **Confirmed:** an installation name identifies one App/Lakebase. Repeat invocation resumes or updates it while preserving state; another name creates another fresh installation. Fail unknown collisions rather than adopt resources. | Every invocation creates another installation. |
| Q8: which owner usage limits? | **Confirmed:** disable the fresh shared owner's stock usage cap to match the live app. | Retain stock limits of ten documents and one private corpus. |

The native extraction task already invokes grounding after saving a successful
answer, and grounding failure is best-effort. Human correction presently calls
the deterministic matcher. Machine repair can use this task boundary without
adding paid calls to GraphQL or PDF-view reads. Persist requests/configuration
before invocation and responses before projection; reuse saved responses after
interruption, and keep unknown invocation outcomes unresolved rather than
silently calling the model again.

Normal human corrections use `corrected_data` and may show the native
original-value action. Machine-selected replacement evidence must be stored
separately. A newer human correction retains precedence if original grounding
completes later. Separate excerpts/pages must use retained source words and
ordinary evidence rendering, not the experiment's display-copy labels.

For Q7, provision the new App/Lakebase before final staging because the archive
configuration requires the generated App origin. Use another installation ID
for QA, with independent resources and no data transfer to delivery. Repeated
definition loading must check exact installed configuration instead of replacing
native edits.

## Definition package baselines

Preserve these installed experiment 95 snapshots unless the owner selects a
new version; verify their manifests and all declared files before loading.

| Workflow | Owner version | Manifest SHA-256 | Definition counts |
| --- | --- | --- | --- |
| Terms | `3.0.0-20261005` | `f120f1e0751117bcefda288e4ec5ed760455020760a6dabf030a77a990312e40` | 32 columns, 38 labels |
| FSPO | `fspo-column-v3` | `2a573fd4d5a13d56752ca9260ea93d8d5cc372879f4f294c59e2022ca250aa49` | 17 columns, 28 labels |

Terms includes its approved v3 label policy. FSPO has no exported policy; do not
invent domain rules or import its experimental evidence-display workaround.
Definitions-only installation does not bind a corpus policy. When a user later
selects the corresponding installed Fieldset/LabelSet for a corpus, policy
binding must follow its verified package. Generic quotation rendering must also
work for packages without a domain label policy.

## Operational prerequisite

The supported CLI and explicit profile are resolved. New named delivery and QA
Apps and Lakebase projects have been provisioned separately. Private journals
retain ownership and resource identities. Do not import historical experiment
operator-context modules, which initialize access to the retained app database.
Deployment verification is recorded separately once the new releases pass their
gates and hosted acceptance.

## Source pointers

- [Recorded live release](https://github.com/pi-squared/OpenContracts-Databricks/blob/171f7a0f31e71a629e00003fd88a632c7a10de79/docs/verification/2026-10-07-issues37-40-live-release.md).
- [Experiment 95](https://github.com/pi-squared/OpenContracts-Databricks/issues/95)
  and [production serving requirement](https://github.com/pi-squared/OpenContracts-Databricks/issues/94).
- DocumentAnalysis: `tools/prepare_upstream.py`, `tools/stage_app.py`,
  `tools/verify_staged_runtime.py`, `tools/install_workflow_package.py`,
  `port/python/databricks_port/workflows.py` and `domain_labels.py`.
- Native API: `config/graphql/extracts_mutations.py`, `labels_mutations.py`,
  `corpuses_mutations.py` and `config/graphql/schema.graphql`.
- [Lakebase bundle provisioning](https://docs.databricks.com/aws/en/oltp/projects/manage-with-bundles)
  and [managed App identity](https://docs.databricks.com/aws/en/oltp/projects/databricks-apps).

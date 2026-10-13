# Ordered stock patches

Apply the entries in `upstream.lock.json` only at its exact stock commit and in
listed order. Preparation checks every patch hash, applies each patch with a
preceding `git apply --check`, then verifies final target hashes and protected
stock files. Python/frontend additions are separately declared overlays.

Patches 0001–0014 and their companion additions reproduce the maintained live
release 0015 at `171f7a0f31e71a629e00003fd88a632c7a10de79`. Their original
verification lives in [the source port](https://github.com/pi-squared/OpenContracts-Databricks/tree/171f7a0f31e71a629e00003fd88a632c7a10de79/docs/verification).
This fork adds 0015–0018. Current verification and deployment instructions are
in [the recipe](../README.md); historical acceptance does not verify a new
installation by itself.

| Patch | Responsibility |
| --- | --- |
| [0001-lakebase-migration-privileges.patch](0001-lakebase-migration-privileges.patch) | Lakebase migration privileges. |
| [0002-extract-source-navigation.patch](0002-extract-source-navigation.patch) | Extract source navigation. |
| [0003-readable-finding-cells.patch](0003-readable-finding-cells.patch) | Readable finding cells. |
| [0004-independent-parser-artifacts.patch](0004-independent-parser-artifacts.patch) | Independent parser artifacts. |
| [0005-installed-workflow-response-models.patch](0005-installed-workflow-response-models.patch) | Installed workflow response models. |
| [0006-structured-claude-temperature.patch](0006-structured-claude-temperature.patch) | Structured Claude temperature. |
| [0007-three-retrieval-rounds.patch](0007-three-retrieval-rounds.patch) | Three retrieval rounds. |
| [0008-selected-quotation-evidence.patch](0008-selected-quotation-evidence.patch) | Selected quotation evidence. |
| [0009-ui-evidence-navigation.patch](0009-ui-evidence-navigation.patch) | UI evidence navigation. |
| [0010-domain-evidence-labels.patch](0010-domain-evidence-labels.patch) | Domain evidence labels. |
| [0011-document-extract-annotation-ownership.patch](0011-document-extract-annotation-ownership.patch) | Document/extract annotation ownership. |
| [0012-grid-source-navigation-without-dialog.patch](0012-grid-source-navigation-without-dialog.patch) | Grid source navigation without dialog. |
| [0013-rejected-finding-evidence.patch](0013-rejected-finding-evidence.patch) | Rejected finding evidence. |
| [0014-parsed-text-location-wording.patch](0014-parsed-text-location-wording.patch) | Parsed-text location wording. |
| [0015-automatic-retained-word-grounding.patch](0015-automatic-retained-word-grounding.patch) | Automatic retained-word quotation repair. |
| [0016-generic-quotation-evidence.patch](0016-generic-quotation-evidence.patch) | Generic quotation evidence rendering. |
| [0017-graphql-schema-parity.patch](0017-graphql-schema-parity.patch) | Served GraphQL schema parity. |
| [0018-defer-empty-personal-corpus.patch](0018-defer-empty-personal-corpus.patch) | Defer the empty personal corpus to first upload. |

| [0019-ingestion-readiness.patch](0019-ingestion-readiness.patch) | Shared extraction readiness, truthful source failure and original PDF access. |

Patch 0017 deliberately regenerates the served GraphQL SDL and is verified by
the native schema parity test.

The new grounding boundary preserves native machine findings and human correction
semantics. Generic quotation rows carry per-finding ownership and active state;
no experimental display-copy labels or changed-highlight notices are introduced.
The configured Warp wheel has its own [dependency patches](../port/dependencies/warp/README.md).

Project UI patches 0021–0048 address the selected [UI issue inventory](../../docs/verification/2026-10-12-project-ui.md). They preserve the stock tree and apply after the Docling jobs recipe. Companion overlays provide keyboard containment, standard Excel downloads and measured PDF label placement. Hosted acceptance is recorded separately from local checks.

Patches 0039 and 0040 correct hosted acceptance findings: dialog autofocus no longer steals the launcher reference, and the extract detail query requests the PDF availability used by its source action.

Patch 0041 preserves the tree-queryset keyword contract needed to disable tree ordering for library sorts. Patch 0042 names the extract dialog close control.

Patch 0043 invalidates document searches after upload, including inactive empty results. Patch 0044 saves ordinary summaries through the canonical Readme.CAML version writer in the same transaction as metadata, retaining the existing article owner rule.

Patches 0045–0047 resolve review findings: truthful completion wording, active child-dialog focus, and shared full-page/corpus extract progress, source navigation and tab downloads. Label/download constants are named in the upstream constants module.

Patch 0048 distinguishes selected document rows from extracted results in the embedded Data header. The shared progress overlay groups cells once, and nested dialog cleanup restores focus to a remaining parent when its launcher disappears.

Patch 0049 implements the source-inspection focus and label visibility contract in [issue #121](https://github.com/pi-squared/OpenContracts-Databricks/issues/121). The companion `useEvidenceFocus` overlay keeps one transient focus separate from viewer selection, retains explicit label modes, and preserves native source navigation. Hidden labels leave measured placement, while active hover keeps separate controls reachable. The composed transition regressions and `test_evidence_focus_browser.py` verify the native screen with synthetic GraphQL/PDF decoding boundaries; hosted acceptance is recorded separately.

Patch 0050 delivers the PDF mouse inspection path in [issue #122](https://github.com/pi-squared/OpenContracts-Databricks/issues/122). The companion `usePdfEvidenceInteraction` overlay finds eligible page-local geometry at the actual pointer point, deduplicates annotation identities and advances stable focus without revising viewer selection or navigation. Shared hover reveals every associated label. The native drawing module anchors labels separately above highlight surfaces and raises the label being used above its neighbors, keeping each displayed control reachable. Native text selection starts after movement and works when a drag begins on saved evidence; stationary background activation clears evidence focus. The native fullscreen viewer permits PDF gestures while child dialogs and controls retain interaction ownership. Add link uses the viewer's existing child-dialog layer so its native input, validation and cancellation remain reachable above that shell. The composed mouse browser campaign verifies geometry, source-card emphasis, exclusions, selected-only display, separate controls, dense overlapping bounds and native gestures through that shell. Deployed acceptance remains a separate gate.

Patch 0051 implements the inspection lifecycle in [issue #123](https://github.com/pi-squared/OpenContracts-Databricks/issues/123). Manual and sidebar zoom preserve the point being read instead of replaying a handled source destination. Source inspection in selected-only mode retains its existing viewer members and filters. The composed regressions and browser runner's `--campaign lifecycle` cover native label exclusions, remembered focus under all modes, multipage labels, explicit navigation, pane transitions and the source-version picker. Hosted acceptance remains a separate gate.

Patch 0052 adds keyboard and touch inspection in [issue #124](https://github.com/pi-squared/OpenContracts-Databricks/issues/124). Native highlight targets reveal temporary labels on keyboard focus, and Enter/Space reuse the page-point overlap cycle. Temporary ownership includes separate label controls and their native editor; cancellation restores the launcher. Native annotation actions become keyboard reachable, and cancelling their protected confirmation returns to the persistent launcher. Escape first cancels the applicable native dialog, filter, viewer settings, action cloud or text-selection gesture before clearing PDF evidence focus. Stationary touch retains the browser's single compatibility-click path; moved, held, cancelled and multi-touch gestures cannot admit an evidence click. Saved highlights admit native held-touch text selection and discard cancelled holds. The composed `--campaign input` checks actual keyboard traversal, label controls, overlap activation, native mode/filter/zoom/pane transitions, touch taps, blank clearing, native gestures and clipboard copying. Deployed oc-qa acceptance remains a separate gate.

Patch 0053 resolves the whole-branch review conventions for [issue #120](https://github.com/pi-squared/OpenContracts-Databricks/issues/120). The native constants module names the unchanged evidence movement, hover-transfer, held-touch and annotation stacking values. The `pdfEvidenceInteraction` utility shares control ownership while retaining anchors only for activation and native selection admission. The native PDF architecture rule documents singular focus, explicit navigation, temporary label ownership, eligibility and gesture/Escape precedence. Existing interaction behavior and the ordered patches 0049–0052 remain intact; the retained composed frontend and browser campaigns verify the assembled correction source.

Patch 0054 adapts the retained partial-results fix from [issue #105](https://github.com/pi-squared/OpenContracts-Databricks/issues/105), originally delivered at `642ba533d689a5cdbf2322ba1bc45fcf2dc9cf43`, to the current shared extract interfaces. A stopped extract retains completed findings, review controls and source navigation even when its parent has an error. Shared lifecycle summaries distinguish completed, failed, interrupted, pending and unreported fields; failed fields retain any saved value without becoming successful or editable. The existing failure dialog and source-readiness notice remain available. Follow-up extraction uses Iterations instead of restarting the saved run from its failure notice. Success percentages use the expected document/field count and exclude failed cells.

The maintained partial-results regressions cover the shared, corpus and full-page native detail views, failed parents with and without a finish timestamp, saved failed-field values, pending and missing fields, and all-failed runs. The composed document/PDF regression follows a retained completed field into its quotation cards and verifies that focused labels remain visible while the other labels wait for hover. Patches 0049–0053 and their declared PDF interaction bytes remain intact. Assembly and hosted acceptance for the Git testing release are tracked in [issue #126](https://github.com/pi-squared/OpenContracts-Databricks/issues/126).

Patch 0055 resolves the #126 review finding by lifting the identical terminal outcome summary and recovery guidance into one native `ExtractOutcomeNotice` component. Both detail screens retain their existing completion condition, counts, wording and error guidance. Patch 0054 and the PDF interaction source remain unchanged; the existing composed regressions verify the presentation refactor.

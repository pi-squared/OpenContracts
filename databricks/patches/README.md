# Ordered stock patches

Apply the entries in `upstream.lock.json` only at its exact stock commit and in
listed order. Preparation checks every patch hash, applies each patch with a
preceding `git apply --check`, then verifies final target hashes and protected
stock files. Python/frontend additions are separately declared overlays.

Patches 0001–0014 and their companion additions reproduce the maintained live
release 0015 at `171f7a0f31e71a629e00003fd88a632c7a10de79`. Their original
verification lives in [the source port](https://github.com/pi-squared/OpenContracts-Databricks/tree/171f7a0f31e71a629e00003fd88a632c7a10de79/docs/verification).
This fork adds 0015–0016. Current verification and deployment instructions are
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

The new grounding boundary preserves native machine findings and human correction
semantics. Generic quotation rows carry per-finding ownership and active state;
no experimental display-copy labels or changed-highlight notices are introduced.
The configured Warp wheel has its own [dependency patches](../port/dependencies/warp/README.md).

# Maintained Warp dependency

Issue [#39](https://github.com/pi-squared/OpenContracts-Databricks/issues/39)
uses Warp-Ingest 2.1.0 with a reproducibly assembled local version,
`2.1.0+oc39.1`. [The dependency lock](lock.json) pins the stock wheel, patch
bytes, original and final source hashes, and six English NLTK resources.
This dependency ledger is independent of the OpenContracts upstream patch list.

The same lock pins RapidOCR 1.4.4 and assembles `1.4.4+oc39.1`. Its only changes
are version metadata, the dependency requirement from desktop OpenCV to the
already pinned `opencv-python-headless==5.0.0.93`, and reconstructed `RECORD`
checksums. OCR code, configuration and bundled ONNX weights remain identical.
Only headless OpenCV is installed; runtime checks reject the desktop package.

| Patch | Reason |
| --- | --- |
| [0001-separate-columns.patch](0001-separate-columns.patch) | The exact owner-selected experimental patch separates prose/form panels and independently ruled tables, retaining genuine tables and legitimate column continuation. Its SHA-256 is `b84a569983ca0449687d499c2ab85c76cd0517f63434bce1b28e3a29a599f27f`. |
| [0002-preserve-column-token-references.patch](0002-preserve-column-token-references.patch) | Column-major blocks and row-major word tokens make global text alignment drop one repeated financial value in the original regression. Retain a dropped word beside a block in its own confirmed column as a separate structural passage with its original word geometry. Do not infer which label or identical value it belongs to. |

Build-time assembly applies both patches to the exact stock wheel and verifies
the final bytes. It replaces the wheel's version metadata and reconstructs
every `RECORD` checksum with fixed ZIP timestamps. No stock dependency is
modified in place. Different wheel, source, patch or language-resource bytes
fail before the dependency bundle is written.

```bash
python tools/build_warp_runtime.py \
  --wheel /absolute/warp_ingest-2.1.0-py3-none-any.whl \
  --rapidocr-wheel /absolute/rapidocr_onnxruntime-1.4.4-py3-none-any.whl \
  --nltk-data /absolute/frozen-nltk-data \
  --destination /absolute/fresh-warp-bundle
```

Staging takes the same three verified inputs through `--warp-wheel`,
`--rapidocr-wheel` and `--warp-nltk-data`. Both exact local wheels travel under
`vendor/` inside the source archive, together with the six resources and runtime
receipt. The archive's verified 8 MiB parts keep every deployed file below the
unchanged Databricks file limit, including the wheel and large ONNX weights.
`release.json` retains the full wheel hashes and the shared installer hash.

Base requirements install pinned core/OCR dependencies and `pip==24.0` before
the app command. The launcher verifies both wheels and installs them offline
with no index, dependency resolution or cache into its new ephemeral source
directory. The same staged installer runs before gate imports and the required
launcher control. Neither step modifies the base interpreter's packages.
The source directory is also the parser worker's import path after its second
directory change. Model bytes remain unchanged; assembly and installation
invoke no models and require no credentials or private volume paths.

The native parser path is
`opencontractserver.pipeline.parsers.warp_local_parser.WarpLocalParser`.
Select it explicitly in the database's `PipelineSettings.preferred_parsers`
entry for `application/pdf`; settings alone do not replace an existing database
selection. Keep existing alternatives available. Its native component settings
expose `apply_ocr`, `disable_ocr`, `semantic_units` and `include_images`.
The accepted default uses automatic local OCR, semantic units and no images.

Each invocation validates the installed distribution's source files and staged
resources before importing Warp, then runs it in a separate process with bounded
threads. English resources and OCR model weights are already available locally;
parsing needs no downloads. Runtime source drift and stock Warp substitution
fail clearly. The wrapper validates the export against the original page
dimensions, records source, parser, settings and export hashes, and uses the
parse artifact identity for its structural annotation set.

Use a fresh source version for reparsing. The adapter refuses to overwrite a
document already linked to a retained structural annotation set. It changes
no existing model quotation or review outcome. Ordinary repeat-upload handling
remains native OpenContracts behavior, so a technical acceptance copy needs
unique source bytes to avoid reusing an earlier parse.

The original-source and two synthetic-control checks are described in
[the verification receipt](../../../docs/verification/2026-10-07-issue39-parser-integration.md).
Word coverage does not establish complete text recovery from images, broad
parser accuracy, substantive correctness or human approval. The earlier
page-1/page-3 image-text omissions, page-8 form association and model-reported
page discrepancy remain separate limits. This change does not resolve #36.

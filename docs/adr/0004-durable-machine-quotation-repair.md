# Durable machine quotation repair

Status: accepted by the owner's Q5–Q8 answers on 8 October 2026.

Run quotation repair at the existing successful machine-field boundary. Retain
the original finding and exact quotation matches. For unresolved quotations,
persist an admission, effective request and settings before one model invocation,
then persist its response before projection. An interrupted or failed invocation
is not automatically repeated. Projection can recover from its saved response.

Use experiment 95's top-five word/word-pair TF-IDF passage ranking and quotation
selection instructions. The model returns text only. Retained word coordinates
and independent exact matching determine location. Separate excerpts/pages stay
separate; ambiguity or incomplete grounding leaves the finding unresolved.

Keep repair state in `evidence_anchors.machineRepairs`. Do not publish parent
extract copies or write machine repair into `corrected_data`. Reviewer edits use
the deterministic matcher and always take precedence, including when a model
response arrives later. Generic evidence annotations belong to one datacell;
ordinary annotation reads hide superseded evidence without deleting source
history. Existing domain-label association lifecycle remains authoritative for
policy-generated annotations.

A named installation and its private ownership journal identify a stable App
and new Lakebase project. Repeat provisioning preserves them; another name
creates another installation. Unknown collisions fail. A separate QA installation
holds verification documents, leaving delivery empty except for definitions.

This pilot retains eager native task execution. A durable background queue and
hosted MLflow synchronization remain separate work. Request capture in Lakebase
protects repair admission but does not imply semantic assessment validation.

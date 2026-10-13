# OpenContracts Databricks port

## Language

**Fresh installation**:
An independent application with no inherited source documents, analysis results,
extractions or review history. Workflow definitions may be installed separately.
_Avoid_: Virgin app

**Definition installation**:
Adding workflow questions, response schemas and label sets without importing
documents, findings or processed evidence.

**Workflow package**:
A versioned domain-owned set of questions, response schemas, validators and
label definitions consumed by the shared application.

**Original finding**:
The retained assessment proposal, including its original evidence quotations.

**Replacement evidence**:
Source passages automatically selected in place of an unlocated quotation for
the same finding, while its original quotation remains retained.

**Corrected finding**:
A reviewer's revision of an original finding, including any revised evidence
quotations.

**Grounded quotation**:
An evidence quotation associated with a passage in its source document. The
association establishes location, not substantive correctness or approval.

**Viewer selection**:
The set of annotations chosen in the document viewer for source inspection.
Selection does not change a finding's evidence quotations or domain labels.

**Focused evidence**:
The single evidence annotation singled out for current source inspection within
its source version, distinct from viewer selection and recorded review outcomes.

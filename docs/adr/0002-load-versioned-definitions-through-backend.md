# Load versioned definitions through the application backend

Keep the existing Fieldset schemas, including nested response models and
validators, and LabelSet definitions as versioned packages in a Databricks volume.
Provide a simple backend loading command controlled by tooling outside the
deployed repository. The owner selected this route because native GraphQL cannot
fully transfer the existing validators; GraphQL installation is not required.

Adapt the existing package installer for definitions-only loading. A
deployment-controlled loader may run inside the app after migrations using the
app's identity. Delivery installs only the Fieldsets and LabelSets; it creates no
workflow corpora or automatic-analysis bindings. Verify package versions,
prevent duplicate installation and reject silently overwriting edits. Import no
PDFs, extracts, findings or processed results.

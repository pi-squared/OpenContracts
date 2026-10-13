# Promote a development recipe to a Git-backed testing app

The canonical application is the pinned recipe in `pi-squared/OpenContracts`.
Development candidates may live in `OpenContracts-Databricks`; do not merge their
full fork-derived trees into that repository's recipe `main`. The controllers
below promote selected maintained source and a verified, self-contained runtime
to the canonical fork's `testing/databricks-port` branch. They leave its stock
application tree intact.

Issue [126](https://github.com/pi-squared/OpenContracts-Databricks/issues/126)
owns the first combined delivery: the `d3c1af66` evidence-label work and the
retained partial-results fix from #105. Patch 0054 adapts the latter to the newer
shared extract interfaces. Maintenance branch `ae3edd1b` supplies the repository
map and setup audit; its earlier recipe does not replace this 54-patch recipe.
Patch 0055 shares the terminal outcome notice between native detail screens.
The fork's Issues remain disabled, so implementation evidence stays in the Port
tracker.

## Private inputs and ownership

Use the existing toolchain: Python 3.11, the locked runtime environment, Node
22.16+, Corepack/Yarn, the pinned parser wheels/assets and Databricks CLI 1.20+.
Select a workspace profile explicitly. Keep credentials, build directories,
installation profiles, journals, gates and detailed verification receipts private.

An `opencontracts-existing-installation.v1` JSON profile explicitly selects:

- `source_app`: the existing app's name, immutable ID, service-principal client
  ID and complete resource bindings captured before attachment.
- `lakebase`: its exact `branch`, `database`, `endpoint`, `schema` and
  `schema_owner_role`; the database and schema are referenced, never managed for
  deletion, reset or ownership transfer.
- `git_repository`: `https://github.com/pi-squared/OpenContracts.git` and provider
  `gitHub`.
- `configuration_secret`: a new installation-owned secret scope/key.
- `runtime_configuration`: `OPENCONTRACTS_SCHEMA`, `PILOT_USERNAME`,
  `WORKFLOW_PACKAGE_ROOT`, `WORKFLOW_INSTALL_HASHES` and `DATABRICKS_TOOL_STRICT`.
  The controller derives the new app's origin and
  `OPENCONTRACTS_DATABASE_MODE=existing` into private bound configuration without
  changing the selected profile bytes or their journaled hash.
- Optional `docling`: the explicitly authorized `run_as_principal`, existing
  `rapidocr_wheel` volume URI and `artifact_volume`.

The profile preserves existing workflow hashes and native definition IDs; it
contains no domain questions or schemas. The application loads hash-verified
packages from the attached definition volume. A retained fieldset can reference
another installed package beyond the configured startup installation list;
preserve that definition and its package too.

The private journal identifies one new app. Unknown app, secret or parser-job
collisions fail. Reruns reuse that app and its configuration. An app attached to
the same database sees the same research: subsequent user edits are shared.

## Provision and configure

Use the existing deployment controller for each stage. `INSTALLATION`, `STATE`,
`PROFILE_JSON`, `CLI` and `WORKSPACE_PROFILE` below are explicitly selected local
values, not tracked configuration.

```bash
python databricks/tools/deploy_installation.py \
  --cli "$CLI" --profile "$WORKSPACE_PROFILE" \
  --installation "$INSTALLATION" --state-directory "$STATE" \
  provision --existing-profile "$PROFILE_JSON"

python databricks/tools/deploy_installation.py \
  --cli "$CLI" --profile "$WORKSPACE_PROFILE" \
  --installation "$INSTALLATION" --state-directory "$STATE" \
  authorize-existing --existing-profile "$PROFILE_JSON"

python databricks/tools/deploy_installation.py \
  --cli "$CLI" --profile "$WORKSPACE_PROFILE" \
  --installation "$INSTALLATION" --state-directory "$STATE" \
  configure-existing --existing-profile "$PROFILE_JSON"
```

Provisioning creates only a stopped Git-backed app and references the selected
Lakebase. Creation can briefly report `STARTING` while its principal and resource
bindings appear. The controller journals the owned App ID and polls for up to
120 seconds, with each read bounded by the remaining deadline. It confirms
`STOPPED`, the principal, Git identity and complete planned bindings. Ownership
or identity movement, active compute and terminal errors stop immediately.
A readiness timeout retains the pending identity for a safe rerun; it never
recreates, moves or starts the app.

Authorization grants schema `USAGE`, all retained table `SELECT`, `INSERT`,
`UPDATE`, `DELETE`, and sequence `USAGE` plus `SELECT` directly to the new app
role. It verifies actual privileges on every retained relation, unchanged schema
and relation owners, and unchanged migration state before recording success.
Sequence readback accepts `SELECT` plus either `USAGE` or `UPDATE` for `nextval`.
It never delegates membership in the managed owner role. Any missing privilege
rolls back the whole grant transaction and leaves publication blocked.
Authorization and startup independently execute one hash-pinned privilege
policy packaged under `databricks_port`, so its imports work from the staged
archive alone. Startup checks its current database role; authorization binds the
selected app role. Grant authority remains separate from effective access.

Some Lakebase operators can grant table access but lack sequence grant options
on app-owned sequences. The authorized retained owner must separately grant
`USAGE, SELECT ON ALL SEQUENCES IN SCHEMA <retained schema>` to the new app role,
then rerun `authorize-existing`. The controller does not impersonate that owner
or grant administrator membership. Configuration and local build/Git promotion
can proceed while this prerequisite is pending; `publish-git` requires verified
database access and configured bindings.

Existing database mode checks schema, port metadata, signing key, relation
privileges, the complete pinned migration graph, active retained pilot user and
registered package/native definitions under read-only startup transactions.
It reads native permissions without creating definitions or rewriting grants.
Missing state, pending migrations, package/definition drift or permission drift
refuses startup. A future schema or package revision must first be migrated and
registered separately by the retained owner. Omitted database mode defaults to
`owned`, preserving ordinary installation creation and migrations.

Configuration creates a private secret resource for the origin, owner, schema,
mode and package settings. The Git runtime contains only its resource reference
and a validated configuration loader.

When Docling is configured, the controller creates an independent source-bound
job for the new app. It uploads only the two hash-addressed parser code files,
reads them back byte for byte on creation and every configuration rerun, and
checks the new job's effective settings. Changed owned parser bytes stop before
updating app resources. Readback admits only exact omitted API defaults: task
`disabled=false`, empty `email_notifications`, zero `min_retry_interval_millis`,
`retry_on_timeout=false`, `run_if=ALL_SUCCESS` and zero task `timeout_seconds`;
job-level empty email/webhook notifications and `format=MULTI_TASK`. Requested
settings, task membership and order stay exact. Added schedules, triggers,
compute settings or unknown task fields stop before app resources change. The
journal retains the original requested settings and owned job identity.
This job retains the existing serverless parser/dependency settings and artifact
volume. It is not run during promotion. App deployment itself uses Git, without
uploading an app snapshot to the workspace.

## Verify and build

Commit the reviewed development source and keep its checkout clean. The build
controller uses the private journal for installation settings and the usual
pinned preparation, frozen frontend installation, regressions, type checking,
production build, staging and parser/launcher gate.

```bash
python databricks/tools/build_release.py \
  --development-commit "$DEVELOPMENT_SHA" \
  --installation-state-directory "$STATE" \
  --work-directory "$BUILD" --node-bin "$NODE_BIN" \
  --warp-wheel "$WARP_WHEEL" --rapidocr-wheel "$RAPIDOCR_WHEEL" \
  --warp-nltk-data "$NLTK_DATA" --docling-jobs \
  --source "$VERIFIED_LOCAL_MIRROR"
```

Choose a new build directory for every source. The successful gate must execute
the required staged parser/launcher control with zero skips. The gate identifies
all staged bytes and its maintained verification source. A receipt from another
checkout/interpreter or changed source cannot admit publication.

The default build creates and syncs its own runtime environment, including the
pinned offline installer prerequisite `pip==24.0`. Use
`RUNTIME_PYTHON="$BUILD/runtime-venv/bin/python"` for planning, publication and
later revalidation. An explicitly supplied `--runtime-python` must already have
the complete base requirements; preinstalled parser wheels cannot replace the
gate's actual offline installation into its extracted source directory.

## Plan and promote

Use a clean, isolated canonical-fork checkout on `testing/databricks-port`.
Start the first testing branch from the selected fork baseline; later candidates
replace only the declared recipe/doc paths and generated runtime. Preserve the
previous testing commit as the new commit's parent. Do not force-push.

```bash
python databricks/tools/build_release.py plan-promotion \
  --development-checkout "$DEVELOPMENT_CHECKOUT" \
  --development-commit "$DEVELOPMENT_SHA" \
  --destination-checkout "$TESTING_CHECKOUT" \
  --testing-branch testing/databricks-port \
  --release "$BUILD/release" --receipt "$BUILD/runtime-gate.json" \
  --runtime-python "$RUNTIME_PYTHON" --output "$PROMOTION_PLAN"

python databricks/tools/build_release.py promote \
  --plan "$PROMOTION_PLAN" --output "$PROMOTION_RECEIPT"
```

Planning writes a private declaration and changes no source or remote. Promotion
checks the declaration again, copies tracked maintained source and the exact
gated runtime into `databricks/app`, records safe provenance in
`databricks/promotion.json`, and commits/pushes only that scope. It verifies that
the remote branch equals the complete promoted SHA. Its private immutable
`PLAN.accepted.json` receipt binds the plan hash to that complete commit and tree.
Keep it with the plan. Repeating the same accepted plan and bytes returns the
same commit only when all maintained source hashes and the complete tree still
match. Changed development source, runtime, gate, destination branch or remote
head stops publication, including follow-up commits outside the maintained
recipe. A missing accepted identity requires explicit inspection.

Promotion retains Git's ordinary staged whitespace checks. Only a patch named
and hash-pinned in the recipe may contain the required single-space prefix for
a blank unified-diff context line. The controller verifies its exact staged
bytes, hunk counts and Git patch syntax before applying that exception; added
line whitespace, blank prefixes outside hunks and undeclared patch files fail.
Repository attributes and whitespace configuration remain unchanged.

`databricks/app` is self-contained because Databricks Git subdirectories cannot
read their parent directory. Its parts, launcher, configuration contract,
requirements and hash-bound offline installer are the gated release inventory.
Both pinned vendor wheels are inside the existing source archive and its
verified 8 MiB parts. The gate and launcher use that same installer after base
requirements, placing the exact wheels into their own ephemeral source roots
without changing the base interpreter or fetching dependencies. Each file fits
the platform's 10 MB limit. Source documents, findings, database exports, private
profiles and domain packages are absent.

## Deploy and verify

```bash
python databricks/tools/deploy_installation.py \
  --cli "$CLI" --profile "$WORKSPACE_PROFILE" \
  --installation "$INSTALLATION" --state-directory "$STATE" \
  publish-git --release "$BUILD/release" \
  --receipt "$BUILD/runtime-gate.json" --python "$RUNTIME_PYTHON" \
  --promotion-receipt "$PROMOTION_RECEIPT" --git-checkout "$TESTING_CHECKOUT" \
  --verification-source "$DEVELOPMENT_CHECKOUT/databricks"
```

Publication revalidates the local gate, remote commit, Git runtime, app identity,
all resource bindings and bound-secret metadata before deploying the exact
commit with source path `databricks/app`. It verifies a successful deployment,
the resolved Git SHA and running status. Automatic deploy-on-push is disabled;
source promotion and deployment are separately reviewable actions.

Run the [hosted acceptance protocol](../../docs/test_scripts/testing-git-promotion.md)
in Chromium and Firefox. Verify retained results, failure inspection, original
PDF/source navigation, default hover labels, persistent focus and actual overlap
cycling. Compare package/native IDs and all retained research/media fingerprints
after the last browser closes. Publish only safe sample screenshots and concise
source/acceptance receipts; detailed calls and raw outputs remain private.

## Failure and rollback

Failures stop later stages and retain private diagnostics. Do not relabel an
earlier failed receipt. Inspect unknown resource collisions, unexpected branch
movement, secret changes or parser-job changes explicitly rather than adopting
or overwriting them. An interrupted creation with an unknown outcome requires
inspection; the controller intentionally refuses to guess ownership.

Application rollback redeploys a previous verified testing commit whose runtime
uses this installation's existing bindings/configuration. Rebuild and revalidate
its local gate if the old checkout or interpreter no longer exists. Database
restoration, schema migrations and destructive recovery are separate operations;
source rollback does not restore or reset shared research. Broader installation
and recovery acceptance in issues #13/#4/#6/#7 remains open.

Use a clean checkout at the prior promoted commit and its original promotion
receipt and the retained historical source directory used by that gate. Its
clean checkout must be either the recorded development commit or the prior
testing commit, with every maintained source hash matching the prior promotion.
The gate must still bind that exact directory, interpreter and source inventory.
Explicitly select the freshly inspected current remote testing tip;
the prior commit must be its ancestor. Rollback verifies the prior complete
tree, maintained source and exact gated runtime, and rechecks the current app
identity, resources, configuration-secret metadata and remote tip before
deployment. It deploys the prior SHA without moving a Git branch or changing
database bindings or contents.

```bash
python databricks/tools/deploy_installation.py \
  --cli "$CLI" --profile "$WORKSPACE_PROFILE" \
  --installation "$INSTALLATION" --state-directory "$STATE" \
  rollback-git --release "$PRIOR_BUILD/release" \
  --receipt "$PRIOR_BUILD/runtime-gate.json" --python "$RUNTIME_PYTHON" \
  --promotion-receipt "$PRIOR_PROMOTION_RECEIPT" \
  --git-checkout "$PRIOR_TESTING_CHECKOUT" \
  --verification-source "$PRIOR_VERIFICATION_SOURCE/databricks" \
  --expected-remote-commit "$CURRENT_TESTING_SHA"
```

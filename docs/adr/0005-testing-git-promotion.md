# Promote verified recipes to a Git-backed testing branch

Accepted by the owner's implementation request on 13 October 2026; tracked in
[Port issue 126](https://github.com/pi-squared/OpenContracts-Databricks/issues/126).

Keep the pinned upstream recipe and the existing build/deployment controllers
in the canonical `pi-squared/OpenContracts` fork. A development candidate from
the Port repository promotes its declared maintained recipe and a gated,
self-contained runtime to `testing/databricks-port`. Databricks deploys the exact
verified Git commit from `databricks/app`; app snapshots are not the publishing
source for this track.

The testing app references the explicitly selected existing Lakebase and loads
versioned owner packages through bound configuration. Credentials, database
connection details, installation settings and detailed verification stay private.
New app access does not transfer existing object ownership or manage the database
for destructive lifecycle operations. Sharing the database shares later edits.
The explicit existing database mode grants and verifies ordinary relation
access without managed owner-role delegation. Startup reads retained metadata,
applied pinned migrations, pilot and registered definitions in read-only
transactions. The retained owner must separately apply future migrations,
register new package revisions and supply sequence grants when the approved
operator lacks grant options. Publication remains blocked until actual database
privileges verify; stopped-app configuration and source promotion can proceed.

The first candidate combines `d3c1af66`'s evidence-label behavior with #105's
retained partial-results fix using ordered patch 0054. This decision does not
merge full fork-derived source into the Port recipe `main`, adopt a parser or
complete the broader installation/recovery issues. See the
[repeatable workflow](../../databricks/docs/testing-promotion.md).

# Keep the Databricks port in the owner's OpenContracts fork

The owner selected `pi-squared/OpenContracts` as the canonical home and release
source of the fresh Databricks port. Maintain its pinned upstream assembly recipe
under `databricks/`, preserving the upstream source and applying the ordered
changes during release assembly. This keeps the owner's fork as the deployment
source while making upstream upgrades reviewable; the existing DocumentAnalysis
repository remains a source of provenance and separate operator tooling.

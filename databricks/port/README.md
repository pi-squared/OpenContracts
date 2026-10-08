# Port assembly

```text
upstream.lock.json
  → prepare_upstream.py: fresh pin + ordered patches + overlays
  → upstream/frontend: Node build and focused integration checks
  → stage_app.py: approved namespaces + frontend/dist + runtime lock/launcher
  → Databricks App: selected endpoints, workflow volume and Lakebase
```

`frontend/` holds hash-bound overlays; `python/` supplies `databricks_port`
and explicit stock pipeline registrations; `runtime/` owns launch/configuration.
[The lock](../upstream.lock.json) is the assembly contract;
[the ledger](../patches/README.md) explains stock departures.

Preparation requires Git/Python, build requires Node 22.16+ and the upstream
lockfile. [Build and deployment](../README.md) explains Python 3.11 runtime
dependencies, the required staged gate, profile selection and resource permissions.

Staging selects `config`, `opencontractserver`, `locale`,
`databricks_port`, explicit overlays and production assets. Tests, operator tools,
source artifacts, fixtures, cassettes and local MLflow dependencies are excluded.
Keep deployed namespaces and historical migrations stable.
Domain packages remain with Terms and FSPO.

[The maintained Warp dependency](dependencies/warp/README.md) has its own wheel,
source, patch and English-resource lock. Staging requires the pinned stock wheel
and frozen NLTK data explicitly, produces the local patched wheel and packages
its parser assets. The native local Warp adapter records independent parse
identities; selecting it for live uploads uses native persisted pipeline settings.

`extraction_readiness.py` owns the shared admission rule used by native mutations,
orchestration, queued field workers and the review UI. It checks complete text,
PDF page coverage and every retained passage’s configured retrieval index before
any model request. The Warp converter recovers zero-area tokens only from unique
original PDF glyph locations and retains strict evidence bounds validation.

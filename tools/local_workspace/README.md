# Persistent local workspace

This optional runtime serves the full application under `/opencontracts/` from
one loopback listener. PostgreSQL and Redis use installation-owned Docker
containers and named volumes. The local Warp service handles native PDF text and
CPU OCR on image-only pages; uploaded files, private configuration, logs, and
process IDs live in the chosen state directory. It has no Databricks dependency.

Install the repository's Python requirements with PyMuPDF and uvicorn, install
the frontend's frozen Yarn dependencies using Node 22, then build:

```sh
cd frontend
OPENCONTRACTS_BASE_PATH=/opencontracts/ yarn build
cd ..
python tools/local_workspace/manage.py start --state /private/opencontracts-state
python tools/local_workspace/manage.py status --state /private/opencontracts-state
python tools/local_workspace/manage.py restart --state /private/opencontracts-state
python tools/local_workspace/manage.py stop --state /private/opencontracts-state
```

Provide `OPENAI_API_KEY` in the process environment before first start. Startup
migrates the database, seeds the embedder's and Warp parser's encrypted settings
without overwriting existing settings, creates the installation owner, installs
any supplied workflow packages, and starts one worker plus the ASGI listener.
The default model is `openai:gpt-6-luna`; embeddings use
`text-embedding-3-small` with 1536 dimensions. System Settings remains the native
place to manage component credentials. No environment-printing command exists.

The first start writes a private `config.json`. Before remote use, set its
`public_origin` to the exact authenticated bridge origin and `owner` to the
intended local account. The default public origin is loopback. Keep the state
directory out of Git and backups containing it private: it contains passwords,
the Django encryption/signing secret, documents, and model output. `stop` retains
the Docker volumes and files; restarting uses the same data. Back up both the
PostgreSQL volume and state directory before upgrading migrations.

Warp's API key is generated into a private `warp.env`; its listener stays on
loopback 4403 and its container is limited to 2 CPUs and 3 GiB. The launcher checks
installation ownership labels before operating existing containers.

## Bridge trust boundary

The ASGI adapter is a **single-owner trusted local service**, not a public
authentication provider. Bind it only to `127.0.0.1`. The remote bridge must
authenticate the allowed user, protect its Tailscale origin with the existing
origin credential, and route HTTP plus WebSockets to this listener. Never expose
the loopback listener directly or accept a client-supplied identity header.

The existing bridge strips Microsoft bearer tokens and browser cookies. For HTTP
API requests, the local adapter discards any supplied bearer/cookie and creates
the installation owner's native application JWT itself. Browser session bootstrap
uses that same native account so subscriptions retain the application's JWT
transport. Provider keys and account passwords never enter browser code.

Supplied HTTP Origin values must exactly match the configured public origin or
the documented loopback origins. Null, duplicate, and unexpected origins fail
before token creation. Requests without Origin are permitted for trusted local
tools and the authenticated bridge's server-side checks. The bridge must enforce
its own exact-origin rule for WebSocket upgrades. Host validation includes only
localhost, loopback, and the configured public hostname. API/media routes preserve
the prefix; the frontend router and build use the same base path.

## Workflows and source selection

Place each verified local workflow package under
`STATE/workflows/<sha256>/manifest.json` and its package files. Startup uses the
native definition installer and the `InstalledWorkflowPackage` ORM registry.
Repeated installation retains user edits and uses normal object permissions.
Workflow data is installation input, not bundled private evidence.
Startup verifies registered packages without rewriting their native definitions.
Valid definition edits are reported in private `bootstrap-report.json` and remain
usable across restart; they are not certified as reproducing the original
package. Invalid package bytes or provenance still fail validation.

This branch starts at upstream `8bc8254d0c03efcf3cdb7b383a675016fcb51351`
and carries selected frontend, retrieval, grounding, and finding-contract work
from the developed application at `e5eeac62ea2afbfd43c57c2d8522d8cefaf04d52`,
including the accepted inline result layout. Current upstream dependencies and
unrelated upstream fixes are retained. Changes use ordinary commits in the fork.

The default PDF route uses the upstream Warp parser/service, including automatic
OCR when pages lack text. The optional PyMuPDF parser reads native text and token
geometry without OCR. OCR results need the same human source review as other
extraction inputs. The Sol reference experiment is separate from application
operation and is not started by this launcher.

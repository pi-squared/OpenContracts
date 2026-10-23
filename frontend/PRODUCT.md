# OpenContracts design workspace

OpenContracts is an application for browsing document collections, reading and
annotating documents, and reviewing structured findings with source citations.
The local workspace runs the React application, Django, PostgreSQL, Redis, and
the extraction worker with persistent data. An authenticated bridge provides
remote access while application services stay on loopback. Workflow definitions
and documents belong to the installation rather than a visual fixture.

Preserve the accepted evidence-first design in DESIGN.md: show readable findings
beside the document, distinguish model outcomes from reviewer decisions, and
retain normal editing, approval, and source-navigation behavior.

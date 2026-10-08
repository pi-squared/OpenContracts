- Recover uniquely matched zero-advance PDF glyph rectangles without changing
  text or token references (`databricks/port/python/databricks_port/parser_exports.py:145`).
- Block extraction from unavailable sources and retain original PDF access during
  ingestion failure (`databricks/port/python/databricks_port/extraction_readiness.py:13`,
  `databricks/port/frontend/SourceReadinessNotice.tsx:5`).

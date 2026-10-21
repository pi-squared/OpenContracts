"""Model-facing citation pages, separate from native annotation coordinates."""

PDF_PAGE_CONVENTION = (
    "one-based physical PDF page; page 1 includes the cover, regardless of "
    "printed page labels; null means unavailable"
)


def citation_page_metadata(document, page_index, geometry=None):
    """Convert a known native PDF index exactly once at the retrieval boundary.

    Non-PDF page/offset sentinels retain their existing meaning. Geometry is
    returned separately by callers and must keep its native zero-based indices.
    For multi-page hits, ``page`` is the annotation's starting page and ``pages``
    lists its geometry pages; neither claims the whole passage fits on one page.
    Missing/invalid starting indices are never inferred from geometry.
    """
    # Shared structural annotations have no document FK. Without verified source
    # type context their native page cannot safely be presented as a citation.
    # Do not guess a document from a shared set or infer PDF type from geometry.
    if document is None:
        return {"page": None}
    if (document.file_type or "").lower() != "application/pdf":
        return {"page": page_index}

    count = document.page_count

    def physical(index):
        if type(index) is not int or index < 0:
            return None
        if type(count) is int and count > 0 and index >= count:
            return None
        return index + 1

    pages = set()
    if isinstance(geometry, dict):
        native_pages = geometry.get("p", {}) if geometry.get("v") == 2 else geometry
        if isinstance(native_pages, dict):
            for key in native_pages:
                # JSON object keys are strings; do not coerce floats or booleans.
                index = int(key) if isinstance(key, str) and key.isdecimal() else key
                page = physical(index)
                if page is not None:
                    pages.add(page)

    return {
        "page": physical(page_index),
        "pages": sorted(pages),
        "page_convention": PDF_PAGE_CONVENTION,
        "geometry_page_convention": "zero-based PDF page indices (native geometry)",
    }

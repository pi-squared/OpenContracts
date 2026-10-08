"""Convert retained parser elements to stock OpenContracts evidence geometry.

AI and Docling provide element rectangles. Each becomes one coarse PAWLS token;
we preserve that resolution rather than manufacturing word-level coordinates.
Warp already emits native OpenContracts data and is validated independently.
"""

import copy
import math
from html.parser import HTMLParser


class TableText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"td", "th", "tr", "p", "br"}:
            self.parts.append(" ")


def table_text(content):
    parser = TableText()
    parser.feed(content)
    return " ".join("".join(parser.parts).split())


def element_export(elements, dimensions, title):
    pages = [
        {"page": {"index": i, "width": width, "height": height}, "tokens": []}
        for i, (width, height) in enumerate(dimensions)
    ]
    annotations = []
    for element in elements:
        text = element["text"]
        if not text.strip():
            continue
        page_index = element["page"]
        if not isinstance(page_index, int) or not 0 <= page_index < len(pages):
            raise ValueError("Parser element references an unknown PDF page")
        left, top, right, bottom = element["bounds"]
        width, height = dimensions[page_index]
        if (
            not all(math.isfinite(v) for v in (left, top, right, bottom))
            or not 0 <= left < right <= width + 0.01
            or not 0 <= top < bottom <= height + 0.01
        ):
            raise ValueError("Parser rectangle is outside the original PDF page")
        token_index = len(pages[page_index]["tokens"])
        pages[page_index]["tokens"].append(
            {
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top,
                "text": text,
            }
        )
        annotations.append(
            {
                "id": str(len(annotations)),
                "annotationLabel": element["label"],
                "rawText": text,
                "page": page_index,
                "annotation_type": "TOKEN_LABEL",
                "structural": True,
                "parent_id": None,
                "annotation_json": {
                    str(page_index): {
                        "bounds": {
                            "left": left,
                            "top": top,
                            "right": right,
                            "bottom": bottom,
                        },
                        "tokensJsons": [
                            {"pageIndex": page_index, "tokenIndex": token_index}
                        ],
                        "rawText": text,
                    }
                },
            }
        )
    if not annotations:
        raise ValueError("Parser output has no text elements")
    return {
        "title": title,
        "description": "Independent parser trial; element-level evidence",
        "content": "\n\n".join(a["rawText"] for a in annotations),
        "page_count": len(pages),
        "pawls_file_content": pages,
        "doc_labels": [],
        "labelled_text": annotations,
        "relationships": [],
    }


def ai_parse_export(raw, dimensions, image_dimensions, title):
    if raw.get("error_status"):
        raise ValueError(
            "AI parser reported page errors; retain rather than import as complete"
        )
    source_pages = raw["document"]["pages"]
    if sorted(p["id"] for p in source_pages) != list(range(len(dimensions))):
        raise ValueError("AI parser page coverage differs from the complete source PDF")
    elements = []
    for item in raw["document"]["elements"]:
        content = item.get("content") or ""
        if not content.strip():
            continue
        boxes = item.get("bbox") or []
        if len(boxes) != 1:
            raise ValueError("Text element needs one unambiguous page rectangle")
        box = boxes[0]
        page = box["page_id"]
        image_width, image_height = image_dimensions[page]
        width, height = dimensions[page]
        if image_width <= 0 or image_height <= 0:
            raise ValueError("Rendered image dimensions are invalid")
        x0, y0, x1, y1 = box["coord"]
        elements.append(
            {
                "text": table_text(content) if item["type"] == "table" else content,
                "label": item["type"],
                "page": page,
                "bounds": (
                    x0 * width / image_width,
                    y0 * height / image_height,
                    x1 * width / image_width,
                    y1 * height / image_height,
                ),
            }
        )
    return element_export(elements, dimensions, title)


def warp_export(raw, dimensions, title):
    export = copy.deepcopy(raw["result"])
    expected_pages = len(dimensions)
    pages = export["pawls_file_content"]
    if (
        export["page_count"] != expected_pages
        or len(pages) != expected_pages
        or [p["page"]["index"] for p in pages] != list(range(expected_pages))
    ):
        raise ValueError("Warp page coverage differs from the complete source PDF")
    if not export.get("content") or not export.get("labelled_text"):
        raise ValueError("Warp has no usable text/structural output")

    def bounds(page, rectangle):
        if not isinstance(page, int) or not 0 <= page < expected_pages:
            raise ValueError("Warp evidence references an unknown PDF page")
        left, top, right, bottom = rectangle
        width, height = dimensions[page]
        if (
            not all(math.isfinite(v) for v in rectangle)
            or not 0 <= left < right <= width + 0.01
            or not 0 <= top < bottom <= height + 0.01
        ):
            raise ValueError("Warp evidence is outside the original PDF page")

    for page, (width, height) in zip(pages, dimensions):
        if (
            abs(page["page"]["width"] - width) > 0.01
            or abs(page["page"]["height"] - height) > 0.01
        ):
            raise ValueError("Warp page dimensions differ from the original PDF")
        for token in page["tokens"]:
            bounds(
                page["page"]["index"],
                (
                    token["x"],
                    token["y"],
                    token["x"] + token["width"],
                    token["y"] + token["height"],
                ),
            )
    for annotation in export["labelled_text"]:
        if not 0 <= annotation["page"] < expected_pages:
            raise ValueError("Warp annotation references an unknown PDF page")
        for key, location in annotation["annotation_json"].items():
            page = int(key)
            box = location["bounds"]
            bounds(page, (box["left"], box["top"], box["right"], box["bottom"]))
            for reference in location["tokensJsons"]:
                token_page, token_index = (
                    reference["pageIndex"],
                    reference["tokenIndex"],
                )
                if token_page != page or not 0 <= token_index < len(
                    pages[page]["tokens"]
                ):
                    raise ValueError("Warp annotation references an unknown page token")
    export["title"] = title
    return export


def docling_export(raw, dimensions, title):
    if raw.get("status") != "success" or raw.get("errors"):
        raise ValueError("Docling did not convert the complete source successfully")
    document = raw["document"]
    if sorted(int(p) for p in document["pages"]) != list(range(1, len(dimensions) + 1)):
        raise ValueError("Docling page coverage differs from the complete source PDF")
    visited, ordered = set(), []

    def visit(reference):
        pointer = reference["$ref"]
        if pointer in visited:
            return
        visited.add(pointer)
        parts = pointer.split("/")
        if (
            len(parts) != 3
            or parts[0] != "#"
            or parts[1] not in {"texts", "tables", "groups", "pictures"}
        ):
            raise ValueError("Unexpected Docling document reference")
        item = document[parts[1]][int(parts[2])]
        if parts[1] in {"texts", "tables"}:
            ordered.append((parts[1], item))
        for child in item.get("children", []):
            visit(child)

    for root in ("body", "furniture"):
        for child in document.get(root, {}).get("children", []):
            visit(child)
    expected = len(document.get("texts", [])) + len(document.get("tables", []))
    if len(ordered) != expected:
        raise ValueError("Docling hierarchy omitted text/table items")
    elements = []
    for kind, item in ordered:
        text = (
            item["text"]
            if kind == "texts"
            else " ".join(
                cell["text"]
                for cell in sorted(
                    item["data"]["table_cells"],
                    key=lambda c: (
                        c["start_row_offset_idx"],
                        c["start_col_offset_idx"],
                    ),
                )
            )
        )
        if not text.strip():
            continue
        provenance = item.get("prov") or []
        if not provenance or (kind == "tables" and len(provenance) != 1):
            raise ValueError(
                "Docling item has no unambiguous text-to-rectangle mapping"
            )
        cursor = 0
        for location in provenance:
            if kind == "texts" and len(provenance) > 1:
                start, end = location.get("charspan", (0, len(text)))
                if (
                    not 0 <= cursor <= start < end <= len(text)
                    or text[cursor:start].strip()
                ):
                    raise ValueError(
                        "Docling character spans overlap or omit source text"
                    )
                segment = text[start:end]
                cursor = end
            else:
                # A single rectangle covers the complete normalized text.
                # List-item spans can include the marker in `orig`, which
                # Docling removes from `text` without changing this rectangle.
                segment = text
                cursor = len(text)
            page = location["page_no"] - 1
            if not 0 <= page < len(dimensions):
                raise ValueError("Docling provenance references an unknown PDF page")
            box = location["bbox"]
            left, right = box["l"], box["r"]
            if box["coord_origin"] == "BOTTOMLEFT":
                top, bottom = (
                    dimensions[page][1] - box["t"],
                    dimensions[page][1] - box["b"],
                )
            elif box["coord_origin"] == "TOPLEFT":
                top, bottom = box["t"], box["b"]
            else:
                raise ValueError("Unknown Docling coordinate origin")
            elements.append(
                {
                    "text": segment,
                    "page": page,
                    "label": item["label"],
                    "bounds": (left, top, right, bottom),
                }
            )
        if text[cursor:].strip():
            raise ValueError("Docling provenance omitted trailing source text")
    return element_export(elements, dimensions, title)

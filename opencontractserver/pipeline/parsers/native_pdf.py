"""Convert native PDF words to the stock parser export without OCR."""


def parse_native_pdf(source, *, title, description=""):
    import pymupdf

    pages, paragraphs, content = [], [], []
    with pymupdf.open(stream=source, filetype="pdf") as pdf:
        if pdf.needs_pass or not pdf.page_count:
            raise ValueError("Native PDF parsing requires an unlocked, nonempty PDF")
        for page_index, page in enumerate(pdf):
            words = page.get_text("words", sort=True)
            text = page.get_text("text", sort=True)
            if not words or not text.strip():
                raise ValueError(
                    f"PDF page {page_index + 1} has no native text; OCR or page review is required"
                )
            tokens: list[dict] = []
            blocks: dict[int, list[int]] = {}
            for word in words:
                # get_text returns unrotated coordinates; Page.rect reflects
                # rotation. Match the original PDF's rendered page geometry.
                # https://pymupdf.readthedocs.io/en/latest/page.html#Page.rotation_matrix
                bounds = pymupdf.Rect(word[:4]) * page.rotation_matrix
                token_index = len(tokens)
                tokens.append(
                    {
                        "x": bounds.x0,
                        "y": bounds.y0,
                        "width": bounds.width,
                        "height": bounds.height,
                        "text": word[4],
                    }
                )
                blocks.setdefault(word[5], []).append(token_index)
            pages.append(
                {
                    "page": {
                        "width": page.rect.width,
                        "height": page.rect.height,
                        "index": page_index,
                    },
                    "tokens": tokens,
                }
            )
            content.append(text)
            for block_index, indices in blocks.items():
                block_tokens = [tokens[index] for index in indices]
                block_text = " ".join(token["text"] for token in block_tokens)
                paragraphs.append(
                    {
                        "id": f"page{page_index}-block{block_index}",
                        "annotationLabel": "Paragraph",
                        "rawText": block_text,
                        "page": page_index,
                        "annotation_type": "TOKEN_LABEL",
                        "structural": True,
                        "parent_id": None,
                        "annotation_json": {
                            str(page_index): {
                                "bounds": {
                                    "top": min(token["y"] for token in block_tokens),
                                    "left": min(token["x"] for token in block_tokens),
                                    "right": max(
                                        token["x"] + token["width"]
                                        for token in block_tokens
                                    ),
                                    "bottom": max(
                                        token["y"] + token["height"]
                                        for token in block_tokens
                                    ),
                                },
                                "tokensJsons": [
                                    {"pageIndex": page_index, "tokenIndex": index}
                                    for index in indices
                                ],
                                "rawText": block_text,
                            }
                        },
                    }
                )
    return {
        "title": title,
        "description": description,
        "content": "\n".join(content),
        "page_count": len(pages),
        "pawls_file_content": pages,
        "doc_labels": [],
        "labelled_text": paragraphs,
        "relationships": [],
    }

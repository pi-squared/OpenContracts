"""Selected quotation locations for the displayed finding version.

Only explicitly named evidence containers supply quotations. Matching permits
typographic punctuation and whitespace changes, never missing or changed words.
Offsets address the complete retained passage, rather than a fuzzy substring.
"""

import json
import unicodedata

PUNCTUATION = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "ʼ": "'",
        "“": '"',
        "”": '"',
        "‐": "-",
        "‑": "-",
        "–": "-",
        "—": "-",
    }
)


def selected_quotes(value):
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    result = []

    def collect(finding, scope=None, path=""):
        if isinstance(finding, list):
            for index, item in enumerate(finding):
                collect(item, scope, f"{path}/{index}")
            return
        if not isinstance(finding, dict):
            return
        context = dict(scope or {})
        for key in ("consumer", "period", "scope", "evidence_scope"):
            if key in finding:
                context[key] = finding[key]
        for key in ("evidence", "evidence_quote"):
            if key not in finding:
                continue
            entries = finding[key]
            if isinstance(entries, str):
                try:
                    entries = json.loads(entries)
                except ValueError:
                    entries = [{"quote": entries, "page": None}]
            if isinstance(entries, dict):
                entries = [entries]
            if not isinstance(entries, list):
                entries = [entries]
            for index, entry in enumerate(entries):
                if isinstance(entry, str):
                    entry = {"quote": entry, "page": None}
                item = (
                    dict(entry)
                    if isinstance(entry, dict)
                    else {"quote": None, "original": entry}
                )
                result.append(
                    {
                        "quote": item.get("quote"),
                        "reportedPage": item.get("page"),
                        "speaker": item.get("speaker"),
                        "scope": context,
                        "selectionPath": f"{path}/{key}/{index}",
                        "original": item,
                    }
                )
        collect(finding.get("scoped_entries", []), context, f"{path}/scoped_entries")

    collect(value)
    return result


def normalized_text(text):
    characters, offsets = [], []
    for index, character in enumerate(text):
        for normalized in unicodedata.normalize("NFKC", character).translate(
            PUNCTUATION
        ):
            if normalized.isspace():
                if not characters or characters[-1] == " ":
                    continue
                normalized = " "
            characters.append(normalized)
            offsets.append(index)
    if characters and characters[-1] == " ":
        characters.pop()
        offsets.pop()
    return "".join(characters), offsets


def locate_finding_evidence(value, pages):
    normalized_pages = [normalized_text(page) for page in pages]
    anchors = []
    for selection in selected_quotes(value):
        anchor = {
            **selection,
            "status": "unmatched",
            "locatedPage": None,
            "matchType": None,
            "annotationId": None,
        }
        quote = selection["quote"]
        if not isinstance(quote, str) or not quote.strip():
            anchors.append({**anchor, "status": "invalid_quote"})
            continue
        target, _ = normalized_text(quote)
        if not target:
            anchors.append({**anchor, "status": "invalid_quote"})
            continue
        hits = []
        for page, (text, offsets) in enumerate(normalized_pages, 1):
            start = 0
            while True:
                position = text.find(target, start)
                if position < 0:
                    break
                end = position + len(target)
                whole_words = not (
                    (target[0].isalnum() and position and text[position - 1].isalnum())
                    or (
                        target[-1].isalnum() and end < len(text) and text[end].isalnum()
                    )
                )
                if whole_words:
                    hits.append(
                        {
                            "locatedPage": page,
                            "start": offsets[position],
                            "end": offsets[end - 1] + 1,
                        }
                    )
                start = position + 1
        reported = selection["reportedPage"]
        preferred = [
            hit
            for hit in hits
            if type(reported) is int and hit["locatedPage"] == reported
        ]
        candidates = preferred or hits
        if len(candidates) == 1:
            hit = candidates[0]
            matched = pages[hit["locatedPage"] - 1][hit["start"] : hit["end"]]
            anchor.update(hit)
            anchor.update(
                status="matched" if preferred else "different_page",
                matchType="exact" if matched == quote else "typography_whitespace",
            )
        elif candidates:
            anchor.update(
                status="ambiguous",
                candidatePages=sorted({hit["locatedPage"] for hit in candidates}),
            )
        anchors.append(anchor)
    return anchors

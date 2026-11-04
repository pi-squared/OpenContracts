import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { OriginalPdfLink } from "../SourceReadinessNotice";
import type { DocumentType } from "../../../types/graphql-api";

let host: HTMLDivElement;
let root: Root;
const documentFixture = {
  id: "document",
  title: "Synthetic agreement",
  slug: "synthetic-agreement",
  creator: { id: "owner", slug: "owner" },
  fileType: "application/pdf",
} as DocumentType;

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

it.each(["/", "/opencontracts", "/impeccable"])(
  "keeps native new-tab navigation inside the %s router basename",
  (basename) => {
    const parentClick = vi.fn();
    act(() => {
      root.render(
        <MemoryRouter basename={basename} initialEntries={[basename]}>
          <div onClick={parentClick}>
            <OriginalPdfLink document={documentFixture} />
          </div>
        </MemoryRouter>
      );
    });
    const anchor = host.querySelector("a")!;
    expect(anchor).not.toBeNull();
    expect(anchor.getAttribute("href")).toBe(
      `${basename === "/" ? "" : basename}/d/owner/synthetic-agreement`
    );
    expect(anchor.target).toBe("_blank");
    expect(anchor.rel).toBe("noopener noreferrer");
    for (const modifiers of [{}, { ctrlKey: true }, { metaKey: true }]) {
      const click = new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        ...modifiers,
      });
      act(() => anchor.dispatchEvent(click));
      expect(click.defaultPrevented).toBe(false);
    }
    expect(parentClick).not.toHaveBeenCalled();
  }
);

it.each([
  { ...documentFixture, slug: undefined },
  { ...documentFixture, creator: undefined },
  { ...documentFixture, fileType: "text/plain" },
])("omits a source link without a routable original PDF", (document) => {
  act(() => {
    root.render(
      <MemoryRouter>
        <OriginalPdfLink document={document as DocumentType} />
      </MemoryRouter>
    );
  });
  expect(host.querySelector("a")).toBeNull();
});

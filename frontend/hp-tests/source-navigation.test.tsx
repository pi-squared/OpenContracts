import { MockedProvider } from "@apollo/client/testing";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ExtractCellFormatter } from "../src/components/extracts/datagrid/ExtractCellFormatter";
import { onlyDisplayTheseAnnotations } from "../src/graphql/cache";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  onlyDisplayTheseAnnotations([]);
  window.history.replaceState(null, "", "/e/owner/extract");
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.restoreAllMocks();
  onlyDisplayTheseAnnotations([]);
});

it("one View Sources click makes one PDF history entry with seventeen mounted cells", async () => {
  const source = {
    id: "source-A",
    document: {
      id: "doc",
      slug: "agreement",
      creator: { id: "owner", slug: "owner" },
    },
    corpus: {
      id: "corpus",
      slug: "terms",
      creator: { id: "owner", slug: "owner" },
    },
  };
  const push = vi.spyOn(window.history, "pushState");
  act(() =>
    root.render(
      <MockedProvider>
        <BrowserRouter>
          {Array.from({ length: 17 }, (_, index) => (
            <ExtractCellFormatter
              key={index}
              cellId={`cell-${index}`}
              value="result"
              cellStatus={{
                isLoading: false,
                isApproved: false,
                isRejected: false,
                isEdited: false,
                correctedData: null,
                originalData: "result",
                error: null,
              }}
              onApprove={() => {}}
              onReject={() => {}}
              onEdit={() => {}}
              readOnly={false}
              isExtractComplete
              schema={{}}
              extractIsList={false}
              row={{}}
              column={{ key: `field-${index}`, name: "Criterion" }}
              cell={{ id: `cell-${index}`, fullSourceList: [source] } as any}
              extract={{ id: "extract" } as any}
            />
          ))}
        </BrowserRouter>
      </MockedProvider>
    )
  );
  act(() =>
    (
      host.querySelector('[aria-label="Cell status actions"]') as HTMLElement
    ).click()
  );
  await act(async () =>
    (host.querySelector('[aria-label="View Sources"]') as HTMLElement).click()
  );
  expect(push).toHaveBeenCalledTimes(1);
  expect(window.location.pathname).toBe("/d/owner/terms/agreement");
  expect(new URLSearchParams(window.location.search).get("ann")).toBe(
    "source-A"
  );
  await act(async () => {
    window.history.back();
    await new Promise((resolve) =>
      window.addEventListener("popstate", resolve, { once: true })
    );
  });
  expect(window.location.pathname).toBe("/e/owner/extract");
  await act(async () => {
    window.history.forward();
    await new Promise((resolve) =>
      window.addEventListener("popstate", resolve, { once: true })
    );
  });
  expect(new URLSearchParams(window.location.search).get("ann")).toBe(
    "source-A"
  );
});

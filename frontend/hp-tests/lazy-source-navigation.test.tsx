import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  InMemoryCache,
  Observable,
} from "@apollo/client";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ExtractCellFormatter } from "../src/components/extracts/datagrid/ExtractCellFormatter";
import { onlyDisplayTheseAnnotations } from "../src/graphql/cache";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
let client: ApolloClient<unknown>;
let requests: Array<{
  variables: Record<string, unknown>;
  resolve: (data: unknown) => void;
  reject: () => void;
}>;

const finding = {
  finding: "supported",
  rationale: "Signature field",
  evidence_quote: '[{"quote":"Owner signature","page":2}]',
};
const evidenceResponse = {
  datacell: {
    id: "cell-0",
    findingEvidence: [
      {
        quote: "Owner signature",
        reportedPage: 2,
        locatedPage: 2,
        status: "matched",
        annotationId: "source-A",
      },
    ],
    fullSourceList: [
      {
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
      },
    ],
  },
};

beforeEach(() => {
  onlyDisplayTheseAnnotations([]);
  window.history.replaceState(null, "", "/e/owner/extract");
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  requests = [];
  client = new ApolloClient({
    cache: new InMemoryCache(),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          requests.push({
            variables: operation.variables,
            resolve: (data) => {
              observer.next({ data });
              observer.complete();
            },
            reject: () => observer.error(new Error("Source access failed")),
          });
        })
    ),
  });
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  client.stop();
  vi.restoreAllMocks();
  onlyDisplayTheseAnnotations([]);
});

function renderCells(correctedData: unknown = null) {
  act(() =>
    root.render(
      <ApolloProvider client={client}>
        <BrowserRouter>
          {Array.from({ length: 17 }, (_, index) => (
            <ExtractCellFormatter
              key={index}
              cellId={`cell-${index}`}
              value={finding}
              cellStatus={{
                isLoading: false,
                isApproved: false,
                isRejected: false,
                isEdited: correctedData !== null,
                correctedData,
                originalData: finding,
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
              column={{ key: `field-${index}`, name: "Agreement signature" }}
              cell={{ id: `cell-${index}`, hasFindingEvidence: true } as any}
              extract={{ id: "extract" } as any}
            />
          ))}
        </BrowserRouter>
      </ApolloProvider>
    )
  );
}

async function viewLazySources(correctedData: unknown = null) {
  renderCells(correctedData);
  expect(requests).toHaveLength(0);
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  act(() =>
    (
      host.querySelector('[aria-label="Cell status actions"]') as HTMLElement
    ).click()
  );
  await act(async () =>
    (host.querySelector('[aria-label="View Sources"]') as HTMLElement).click()
  );
  expect(requests).toHaveLength(1);
  expect(requests[0].variables).toEqual({ id: "cell-0", version: "effective" });
}

it("lazy finding sources make one PDF history entry after evidence arrives", async () => {
  const push = vi.spyOn(window.history, "pushState");
  await viewLazySources();
  expect(push).not.toHaveBeenCalled();
  expect(window.location.pathname).toBe("/e/owner/extract");
  await act(async () => requests[0].resolve(evidenceResponse));
  expect(push).toHaveBeenCalledTimes(1);
  expect(window.location.pathname).toBe("/d/owner/terms/agreement");
  expect(new URLSearchParams(window.location.search).get("ann")).toBe(
    "source-A"
  );
  expect(new URLSearchParams(window.location.search).get("extract")).toBe(
    "extract"
  );
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
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
  expect(window.location.pathname).toBe("/d/owner/terms/agreement");
  expect(new URLSearchParams(window.location.search).get("ann")).toBe(
    "source-A"
  );
  expect(push).toHaveBeenCalledTimes(1);
});

it("#37: View Sources keeps the finding summary closed while evidence is pending", async () => {
  await viewLazySources();
  try {
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  } finally {
    await act(async () => requests[0].resolve(evidenceResponse));
  }
});

it("reports source loading in the clicked cell without a dialog", async () => {
  await viewLazySources();
  expect(host.querySelector('[role="status"]')?.textContent).toContain(
    "Loading source locations"
  );
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  await act(async () => requests[0].resolve(evidenceResponse));
  expect(host.querySelector('[role="status"]')).toBeNull();
});

it("reports source access failure in the cell and retries without a dialog", async () => {
  const push = vi.spyOn(window.history, "pushState");
  await viewLazySources();
  await act(async () => requests[0].reject());
  expect(host.querySelector('[role="alert"]')?.textContent).toContain(
    "Source locations could not be loaded"
  );
  expect(host.textContent).not.toContain("No highlighted source available");
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  expect(push).not.toHaveBeenCalled();
  const retry = Array.from(host.querySelectorAll("button")).find(
    (button) => button.textContent === "Retry source locations"
  );
  expect(retry).toBeDefined();
  await act(async () => retry?.click());
  expect(requests).toHaveLength(2);
  expect(requests[1].variables).toEqual({ id: "cell-0", version: "effective" });
  await act(async () => requests[1].resolve(evidenceResponse));
  expect(push).toHaveBeenCalledTimes(1);
  expect(window.location.pathname).toBe("/d/owner/terms/agreement");
});

it("reports no located source without navigating or opening a dialog", async () => {
  const push = vi.spyOn(window.history, "pushState");
  await viewLazySources();
  await act(async () =>
    requests[0].resolve({
      datacell: { id: "cell-0", findingEvidence: [], fullSourceList: [] },
    })
  );
  expect(host.querySelector('[role="status"]')?.textContent).toContain(
    "No highlighted source available"
  );
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  expect(push).not.toHaveBeenCalled();
});

it("opening finding details while sources load cancels the pending navigation", async () => {
  const push = vi.spyOn(window.history, "pushState");
  await viewLazySources();
  await act(async () =>
    (
      host.querySelector(
        '[aria-label="View finding: Supported"]'
      ) as HTMLElement
    ).click()
  );
  expect(document.body.querySelector('[role="dialog"]')).not.toBeNull();
  expect(document.body.textContent).toContain("Agreement signature");
  await act(async () => requests[0].resolve(evidenceResponse));
  expect(push).not.toHaveBeenCalled();
  expect(document.body.querySelector('[role="dialog"]')).not.toBeNull();
  expect(requests).toHaveLength(2);
  await act(async () => requests[1].resolve(evidenceResponse));
  expect(document.body.textContent).toContain("Owner signature");
});

it("navigates to every located quote with labels enabled", async () => {
  await viewLazySources();
  await act(async () =>
    requests[0].resolve({
      datacell: {
        ...evidenceResponse.datacell,
        fullSourceList: [
          evidenceResponse.datacell.fullSourceList[0],
          { ...evidenceResponse.datacell.fullSourceList[0], id: "source-B" },
        ],
      },
    })
  );
  const params = new URLSearchParams(window.location.search);
  expect(params.get("ann")).toBe("source-A,source-B");
  expect(params.get("labels")).toBeNull();
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
});

it("does not navigate using an original finding's late response after a correction", async () => {
  const push = vi.spyOn(window.history, "pushState");
  await viewLazySources();
  renderCells({ data: { ...finding, rationale: "Corrected assessment" } });
  await act(async () => requests[0].resolve(evidenceResponse));
  expect(push).not.toHaveBeenCalled();
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  act(() =>
    (
      host.querySelector('[aria-label="Cell status actions"]') as HTMLElement
    ).click()
  );
  await act(async () =>
    (host.querySelector('[aria-label="View Sources"]') as HTMLElement).click()
  );
  expect(requests).toHaveLength(2);
  await act(async () =>
    requests[1].resolve({
      datacell: {
        ...evidenceResponse.datacell,
        fullSourceList: [
          {
            ...evidenceResponse.datacell.fullSourceList[0],
            id: "corrected-source",
          },
        ],
      },
    })
  );
  expect(new URLSearchParams(window.location.search).get("ann")).toBe(
    "corrected-source"
  );
  expect(push).toHaveBeenCalledTimes(1);
});

it("an explicit Edit action keeps its dialog open while an obsolete source response arrives", async () => {
  const push = vi.spyOn(window.history, "pushState");
  await viewLazySources();
  act(() =>
    (
      host.querySelector('[aria-label="Cell status actions"]') as HTMLElement
    ).click()
  );
  act(() => (host.querySelector('[aria-label="Edit"]') as HTMLElement).click());
  expect(document.body.textContent).toContain("Edit JSON Data");
  await act(async () => requests[0].resolve(evidenceResponse));
  expect(push).not.toHaveBeenCalled();
  expect(document.body.querySelector('[role="dialog"]')).not.toBeNull();
  expect(document.body.textContent).toContain("Edit JSON Data");
});

it("omits source controls for retained not_found despite stale availability", () => {
  renderCells({ ...finding, finding: "not_found" });
  act(() =>
    (
      host.querySelector('[aria-label="Cell status actions"]') as HTMLElement
    ).click()
  );
  expect(host.querySelector('[aria-label="View Sources"]')).toBeNull();
  act(() =>
    (
      host.querySelector(
        '[aria-label="View finding: Not found"]'
      ) as HTMLElement
    ).click()
  );
  expect(requests).toHaveLength(0);
  expect(document.body.textContent).toContain("Signature field");
  expect(document.body.textContent).not.toContain("Owner signature");
  expect(document.body.textContent).not.toContain("No quotations recorded");
});

it("carries only the inspected original version into PDF navigation", async () => {
  const corrected = { ...finding, finding: "not_found" };
  renderCells(corrected);
  act(() =>
    (
      host.querySelector('[aria-label="Cell status actions"]') as HTMLElement
    ).click()
  );
  act(() =>
    (host.querySelector('[aria-label="View original"]') as HTMLElement).click()
  );
  expect(requests).toHaveLength(1);
  expect(requests[0].variables).toEqual({ id: "cell-0", version: "original" });
  await act(async () => requests[0].resolve(evidenceResponse));
  const quoteButton = Array.from(document.body.querySelectorAll("button")).find(
    (button) => button.textContent?.includes("View quotation")
  );
  expect(quoteButton).toBeDefined();
  act(() => quoteButton!.click());
  const params = new URLSearchParams(window.location.search);
  expect(params.get("findingCell")).toBe("cell-0");
  expect(params.get("findingVersion")).toBe("original");
  expect(params.get("ann")).toBe("source-A");
  expect(corrected.finding).toBe("not_found");
});

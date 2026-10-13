import React, { act, useEffect } from "react";
import { createRoot, Root } from "react-dom/client";
import { BrowserRouter, useLocation } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { Provider, createStore } from "jotai";
import { afterEach, beforeEach, expect, it } from "vitest";
import { SingleDocumentExtractResults } from "../src/components/annotator/sidebar/SingleDocumentExtractResults";
import { dataCellsAtom } from "../src/components/annotator/context/AnalysisAtoms";
import { REQUEST_REJECT_DATACELL } from "../src/graphql/mutations";
import {
  selectedAnnotationIds,
  selectedExtractIds,
  selectedAnalysesIds,
} from "../src/graphql/cache";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  selectedAnnotationIds(["A"]);
  selectedExtractIds([]);
  selectedAnalysesIds([]);
  window.history.replaceState(
    null,
    "",
    "/d/owner/terms/agreement?ann=A&extract=kept&analysis=kept"
  );
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  selectedAnnotationIds([]);
});

function RouteSelection() {
  const location = useLocation();
  useEffect(() => {
    const value = new URLSearchParams(location.search).get("ann");
    selectedAnnotationIds(value ? value.split(",") : []);
  }, [location.search]);
  return null;
}

it("alternating extract sources composes navigation while clearing focus retains selection", async () => {
  const source = (id: string, page: number) => ({
    id,
    page,
    rawText: `Evidence ${id}`,
    annotationType: "TOKEN_LABEL",
    structural: false,
    annotationLabel: {
      id: "label",
      text: "Criterion",
      color: "#2563eb",
      labelType: "TOKEN_LABEL",
    },
    json: {
      [page]: {
        bounds: { left: 10, right: 80, top: 20, bottom: 30 },
        tokensJsons: [],
      },
    },
  });
  await act(async () =>
    root.render(
      <Provider>
        <MockedProvider>
          <BrowserRouter>
            <RouteSelection />
            <SingleDocumentExtractResults
              columns={[{ id: "column", name: "Criterion" } as any]}
              datacells={[
                {
                  id: "cell",
                  column: { id: "column" },
                  data: "result",
                  fullSourceList: [source("A", 0), source("B", 1)],
                } as any,
              ]}
            />
          </BrowserRouter>
        </MockedProvider>
      </Provider>
    )
  );
  act(() =>
    (
      Array.from(host.querySelectorAll("button")).find(
        (e) => e.textContent === "2 Annotations"
      ) as HTMLElement
    ).click()
  );
  for (const id of ["B", "A", "B"]) {
    await act(async () =>
      (
        host.querySelector(`[data-annotation-id="${id}"]`) as HTMLElement
      ).click()
    );
    expect(new URLSearchParams(window.location.search).get("ann")).toBe(id);
    expect(new URLSearchParams(window.location.search).get("analysis")).toBe(
      "kept"
    );
    expect(new URLSearchParams(window.location.search).get("extract")).toBe(
      "kept"
    );
  }
  await act(async () =>
    (host.querySelector('[data-annotation-id="B"]') as HTMLElement).click()
  );
  expect(new URLSearchParams(window.location.search).get("ann")).toBe("B");
  expect(
    host.querySelector('[data-annotation-id="B"]')?.hasAttribute("aria-current")
  ).toBe(false);
});

it("a review-only mutation preserves the loaded heading's quotations and source cards", async () => {
  const store = createStore();
  const source = {
    id: "located-quote",
    page: 0,
    rawText: "Synthetic selected quotation",
    isEvidenceQuote: true,
    annotationType: "TOKEN_LABEL",
    structural: false,
    annotationLabel: {
      id: "criterion",
      text: "Criterion",
      color: "#2563eb",
      labelType: "TOKEN_LABEL",
    },
    json: {
      "0": {
        bounds: { left: 10, right: 80, top: 20, bottom: 30 },
        tokensJsons: [],
      },
    },
  };
  const cell = {
    id: "review-cell",
    column: { id: "review-column" },
    data: { data: "Original finding" },
    correctedData: { data: "Corrected finding" },
    fullSourceList: [source],
    findingEvidence: [{ quote: source.rawText, status: "exact" }],
    approvedBy: null,
    rejectedBy: null,
  };
  await act(async () =>
    root.render(
      <Provider store={store}>
        <MockedProvider
          mocks={[
            {
              request: {
                query: REQUEST_REJECT_DATACELL,
                variables: { datacellId: cell.id },
              },
              result: {
                data: {
                  rejectDatacell: {
                    ok: true,
                    message: "Rejected",
                    obj: {
                      id: cell.id,
                      data: cell.data,
                      correctedData: cell.correctedData,
                      started: null,
                      completed: null,
                      stacktrace: null,
                      column: cell.column,
                      document: { id: "document" },
                      approvedBy: null,
                      rejectedBy: { id: "reviewer", username: "reviewer" },
                    },
                  },
                },
              },
            },
          ]}
        >
          <BrowserRouter>
            <SingleDocumentExtractResults
              columns={[{ id: "review-column", name: "Review heading" } as any]}
              datacells={[]}
            />
          </BrowserRouter>
        </MockedProvider>
      </Provider>
    )
  );
  // The public pane consumes an already loaded heading independently of which
  // parent owns its query. Seed the same retained source-bearing record.
  act(() => store.set(dataCellsAtom, [cell as any]));
  act(() =>
    (
      Array.from(host.querySelectorAll("button")).find(
        (element) => element.textContent === "1 Annotation"
      ) as HTMLElement
    ).click()
  );
  expect(
    host.querySelector('[data-annotation-id="located-quote"]')
  ).not.toBeNull();
  await act(async () => {
    (host.querySelector(".reject") as HTMLElement).click();
    await new Promise((resolve) => setTimeout(resolve, 60));
  });
  expect(
    host.querySelector('[data-annotation-id="located-quote"]')
  ).not.toBeNull();
  expect(host.textContent).toContain("Rejected");
});

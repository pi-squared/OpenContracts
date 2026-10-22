import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { Simulate } from "react-dom/test-utils";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SingleDocumentExtractResults } from "../src/components/annotator/sidebar/SingleDocumentExtractResults";
import { ColumnType, DatacellType } from "../src/types/graphql-api";

const refresh = vi.hoisted(() => ({ loading: false, error: false }));
const focus = vi.hoisted(() => ({
  id: null as string | null,
  request: null as object | null,
}));
vi.mock("../src/components/annotator/hooks/AnalysisHooks", () => ({
  useAnalysisManager: () => ({
    dataCells: [],
    setDataCells: () => {},
    extractResultsLoading: refresh.loading,
    extractResultsError: refresh.error
      ? new Error("Refresh failed")
      : undefined,
    retryExtractResults: async () => {},
  }),
}));
vi.mock("../src/hooks/useEvidenceFocus", () => ({
  useEvidenceFocus: () => ({
    focusedEvidenceId: focus.id,
    focusRequest: focus.request,
    setFocusedEvidence: () => {
      focus.id = null;
      focus.request = null;
    },
    navigateToEvidence: () => {},
  }),
}));
vi.mock("react-json-view", () => ({ default: () => <div>Raw editor</div> }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
const column = { id: "criterion", name: "Hire purchase price" } as ColumnType;
const cell = {
  id: "finding",
  column,
  data: {
    data: {
      finding: "present_blank",
      rationale: "The price is blank.",
      evidence: [],
    },
  },
  correctedData: null,
  fullSourceList: [],
} as unknown as DatacellType;

beforeEach(() => {
  refresh.loading = refresh.error = false;
  focus.id = null;
  focus.request = null;
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
function render(cells = [cell]) {
  act(() =>
    root.render(
      <MockedProvider>
        <MemoryRouter>
          <SingleDocumentExtractResults columns={[column]} datacells={cells} />
        </MemoryRouter>
      </MockedProvider>
    )
  );
}

it("retains an active review and draft through loading, failed and empty refreshes", () => {
  render();
  act(() =>
    host
      .querySelector<HTMLButtonElement>('[aria-label="Edit finding"]')!
      .click()
  );
  const textarea = host.querySelector("textarea")!;
  act(() =>
    Simulate.change(textarea, { target: { value: "Unsaved reviewer comment" } })
  );
  refresh.loading = true;
  render([]);
  expect(host.querySelector("textarea")).toBe(textarea);
  expect(textarea.value).toBe("Unsaved reviewer comment");
  refresh.loading = false;
  refresh.error = true;
  render([]);
  expect(host.querySelector("textarea")).toBe(textarea);
  refresh.error = false;
  render([]);
  expect(host.querySelector("textarea")).toBe(textarea);
  render();
  expect(textarea.value).toBe("Unsaved reviewer comment");
  act(() =>
    host
      .querySelector<HTMLButtonElement>('[aria-label="Close review comments"]')!
      .click()
  );
  expect(host.querySelector('[role="dialog"]')).toBeNull();
});

it("reveals, focuses and scrolls the matching source, including repeat activation", () => {
  const scroll = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: scroll,
  });
  const source = (id: string) => ({
    id,
    page: 0,
    rawText: `Quotation ${id}`,
    annotationType: "TOKEN_LABEL",
    structural: false,
    annotationLabel: {
      id: "label",
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
  });
  const cells = [
    {
      ...cell,
      fullSourceList: [source("A"), source("B")],
    } as unknown as DatacellType,
  ];
  render(cells);
  expect(host.querySelector('[data-annotation-id="B"]')).toBeNull();
  focus.id = "B";
  focus.request = {};
  render(cells);
  const target = host.querySelector('[data-extract-annotation-target="B"]');
  expect(target).not.toBeNull();
  expect(document.activeElement).toBe(target);
  expect(
    host.querySelector('[data-annotation-id="B"]')?.getAttribute("aria-current")
  ).toBe("true");
  expect(scroll).toHaveBeenCalledWith(
    expect.objectContaining({ block: "nearest", inline: "nearest" })
  );
  const toggle = Array.from(host.querySelectorAll("button")).find(
    (e) => e.textContent === "2 Annotations"
  )!;
  act(() => toggle.click());
  expect(host.querySelector('[data-annotation-id="B"]')).toBeNull();
  focus.request = {};
  render(cells);
  expect(document.activeElement).toBe(
    host.querySelector('[data-extract-annotation-target="B"]')
  );
  expect(scroll).toHaveBeenCalledTimes(2);
  act(() => Simulate.keyDown(document.activeElement!, { key: "Escape" }));
  render(cells);
  expect(
    host.querySelector('[data-annotation-id="B"]')?.hasAttribute("aria-current")
  ).toBe(false);
  delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
});

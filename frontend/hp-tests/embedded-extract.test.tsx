import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  InMemoryCache,
  Observable,
} from "@apollo/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CorpusExtractDetail } from "../src/components/extracts/CorpusExtractDetail";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
let client: ApolloClient<unknown>;
let downloads: Blob[];
const createURL = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
const revokeURL = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
const owner = { id: "owner", slug: "owner", username: "owner" };
const doc = {
  id: "doc",
  title: "Public sample",
  slug: "public-sample",
  creator: owner,
  pdfFile: "/sample.pdf",
  fileType: "application/pdf",
  description: "Sample",
  pageCount: 1,
  processingStatus: "COMPLETED",
};
const column = {
  id: "column",
  name: "Finding",
  query: "",
  instructions: "",
  matchText: "",
  limitToLabel: "",
  taskName: "",
  outputType: "str",
  extractIsList: false,
};
function fixture(completed = false) {
  return {
    id: "extract",
    name: "Embedded fixture",
    corpus: { id: "corpus", title: "Corpus", slug: "corpus", creator: owner },
    creator: owner,
    created: "2026-10-12T00:00:00Z",
    started: completed ? "2026-10-12T00:00:01Z" : null,
    finished: completed ? "2026-10-12T00:00:02Z" : null,
    error: null,
    sourceReadinessError: null,
    modelConfig: null,
    iterationAxis: null,
    parentExtract: null,
    fullIterationList: [],
    fieldset: {
      id: "fieldset",
      name: "Fieldset",
      inUse: true,
      fullColumnList: [column],
    },
    fullDocumentList: [doc],
    fullDatacellList: completed
      ? [
          {
            id: "cell",
            document: doc,
            column,
            hasFindingEvidence: false,
            data: null,
            dataDefinition: null,
            started: "2026-10-12T00:00:01Z",
            completed: null,
            failed: "2026-10-12T00:00:02Z",
            correctedData: null,
            stacktrace: null,
            rejectedBy: null,
            approvedBy: null,
          },
        ]
      : [],
  };
}
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  downloads = [];
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: (blob: Blob) => {
      downloads.push(blob);
      return "blob:download";
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: () => {},
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  client?.stop();
  vi.restoreAllMocks();
  for (const [name, descriptor] of [
    ["createObjectURL", createURL],
    ["revokeObjectURL", revokeURL],
  ] as const) {
    if (descriptor) Object.defineProperty(URL, name, descriptor);
    else Reflect.deleteProperty(URL, name);
  }
});
async function render(completed = false) {
  client = new ApolloClient({
    cache: new InMemoryCache(),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          observer.next({
            data:
              operation.operationName === "GetExtract"
                ? { extract: fixture(completed) }
                : {
                    documents: {
                      edges: [],
                      pageInfo: {
                        hasNextPage: false,
                        hasPreviousPage: false,
                        startCursor: null,
                        endCursor: null,
                      },
                    },
                  },
          });
          observer.complete();
        })
    ),
  });
  await act(async () => {
    root.render(
      <ApolloProvider client={client}>
        <MemoryRouter>
          <CorpusExtractDetail extractId="extract" onClose={() => {}} />
        </MemoryRouter>
      </ApolloProvider>
    );
    await new Promise((resolve) => setTimeout(resolve, 25));
  });
}
async function click(name: string) {
  const element = Array.from(
    host.querySelectorAll<HTMLElement>("button,[role=tab]")
  ).find(
    (e) =>
      e.getAttribute("aria-label") === name || e.textContent?.trim() === name
  );
  expect(element, name).toBeDefined();
  await act(async () => element!.click());
}
async function text(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsText(blob);
  });
}
it("keeps unstarted source counts truthful and exposes the original PDF in corpus details", async () => {
  await render();
  expect(host.textContent).toContain("processed of 1 selected");
  expect(host.textContent).toMatch(/0\s*Documents\s*processed of 1 selected/);
  expect(host.textContent).toMatch(/0\s*Rows\s*extracted/);
  expect(host.textContent).toContain("1 selected document rows");
  await click("Documents");
  expect(host.textContent).toContain("Not started");
  expect(host.textContent).not.toContain("1 row extracted");
  expect(
    host.querySelector('[aria-label="Open PDF: Public sample"]')
  ).not.toBeNull();
});
it("identifies partial field failure without making the finished parent unfinished", async () => {
  await render(true);
  expect(host.textContent).toContain("Completed");
  expect(host.querySelector('[role="status"]')?.textContent).toContain(
    "1 failed field"
  );
});
it("downloads the selected embedded schema and iteration formats", async () => {
  await render();
  await click("Schema");
  await click("Export Schema JSON");
  expect(JSON.parse(await text(downloads[0])).columns[0].name).toBe("Finding");
  await click("Iterations");
  await click("Export Iterations JSON");
  expect(JSON.parse(await text(downloads[1])).current).toBe("extract");
});

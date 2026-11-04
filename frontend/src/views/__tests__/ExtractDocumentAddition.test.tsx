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
import { CorpusExtractDetail } from "../../components/extracts/CorpusExtractDetail";
import { ExtractDetail } from "../ExtractDetail";
import { openedExtract } from "../../graphql/cache";
import type { ExtractType } from "../../types/graphql-api";

// Keep both real views, the data grid and Apollo cache/query lifecycle. The
// picker supplies selected IDs without bringing library filtering into this test.
vi.mock("../../components/widgets/modals/SelectDocumentsModal", () => ({
  SelectDocumentsModal: ({
    open,
    onAddDocumentIds,
    toggleModal,
  }: {
    open: boolean;
    onAddDocumentIds: (ids: string[]) => void;
    toggleModal: () => void;
  }) =>
    open ? (
      <div>
        {[1, 4].map((count) => (
          <button
            key={count}
            onClick={() => {
              onAddDocumentIds(
                Array.from({ length: count }, (_, index) => `document-${index}`)
              );
              toggleModal();
            }}
          >
            Add {count} processed PDFs
          </button>
        ))}
      </div>
    ) : null,
}));

let host: HTMLDivElement;
let root: Root;
let client: ApolloClient<unknown>;
let requests: string[];
let selectedIds: string[];
let postAdditionError: string | null;
let mutationSucceeds: boolean;
const owner = { id: "owner", slug: "owner", username: "owner" };
const sourceDocument = (id: string) => ({
  __typename: "DocumentType",
  id,
  title: `Processed ${id}`,
  slug: id,
  creator: owner,
  pdfFile: "/synthetic.pdf",
  fileType: "application/pdf",
  description: "Synthetic processed source",
  pageCount: 1,
  processingStatus: "COMPLETED",
});

function extractFixture() {
  return {
    id: "extract",
    name: "Document addition",
    corpus: null,
    creator: owner,
    created: "2026-11-04T00:00:00Z",
    started: null,
    finished: null,
    error: null,
    sourceReadinessError: selectedIds.length
      ? postAdditionError
      : "Add a processed document before extracting.",
    modelConfig: null,
    iterationAxis: null,
    parentExtract: null,
    fullIterationList: [],
    fieldset: {
      id: "fieldset",
      name: "Fieldset",
      inUse: true,
      fullColumnList: [
        {
          id: "column",
          name: "Finding",
          query: "Find a title",
          instructions: "",
          matchText: "",
          limitToLabel: "",
          taskName: "",
          outputType: "str",
          extractIsList: false,
        },
      ],
    },
    fullDocumentList: selectedIds.map(sourceDocument),
    fullDatacellList: [],
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  requests = [];
  selectedIds = [];
  postAdditionError = null;
  mutationSucceeds = true;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  client?.stop();
  openedExtract(null);
  vi.useRealTimers();
});

async function render(surface: "page" | "corpus") {
  openedExtract({
    id: "extract",
    name: "Document addition",
    created: "2026-11-04T00:00:00Z",
  } as ExtractType);
  client = new ApolloClient({
    cache: new InMemoryCache(),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          requests.push(operation.operationName);
          if (operation.operationName === "GetExtract") {
            observer.next({ data: { extract: extractFixture() } });
          } else if (operation.operationName === "AddDocToExtract") {
            if (mutationSucceeds) selectedIds = operation.variables.documentIds;
            observer.next({
              data: {
                addDocsToExtract: {
                  ok: mutationSucceeds,
                  message: mutationSucceeds ? "" : "Could not add source",
                  // The real mutation intentionally returns no source metadata.
                  objs: selectedIds.map((id) => ({
                    __typename: "DocumentType",
                    id,
                    title: `Processed ${id}`,
                    description: "Synthetic processed source",
                    pageCount: 1,
                  })),
                },
              },
            });
          } else {
            observer.error(
              new Error(`Unexpected operation ${operation.operationName}`)
            );
            return;
          }
          observer.complete();
        })
    ),
  });
  await act(async () => {
    root.render(
      <ApolloProvider client={client}>
        <MemoryRouter>
          {surface === "page" ? (
            <ExtractDetail />
          ) : (
            <CorpusExtractDetail extractId="extract" onClose={() => {}} />
          )}
        </MemoryRouter>
      </ApolloProvider>
    );
    await vi.advanceTimersByTimeAsync(1);
  });
}

function button(label: string) {
  const found = Array.from(host.querySelectorAll("button")).find(
    (candidate) =>
      candidate.textContent?.trim() === label ||
      candidate.getAttribute("aria-label") === label
  );
  expect(found, `button ${label}`).toBeDefined();
  return found!;
}
function startButton() {
  return Array.from(host.querySelectorAll("button")).find(
    (candidate) =>
      candidate.textContent?.trim() === "Start Extract" ||
      candidate.getAttribute("aria-label") === "Start extract"
  )!;
}
async function addDocuments(count: number) {
  await act(async () => {
    button("Add documents").click();
    await vi.advanceTimersByTimeAsync(1);
  });
  await act(async () => {
    button(`Add ${count} processed PDFs`).click();
    await vi.advanceTimersByTimeAsync(1);
  });
}

it.each([
  ["page", 1],
  ["page", 4],
  ["corpus", 1],
  ["corpus", 4],
] as const)(
  "%s refreshes source metadata after adding %i processed PDF(s) without manual Refresh",
  async (surface, count) => {
    await render(surface);
    expect(startButton().disabled).toBe(true);
    await addDocuments(count);
    expect(requests).toContain("AddDocToExtract");
    expect(startButton().disabled).toBe(false);
    expect(host.textContent).not.toContain("Source unavailable.");
    expect(host.textContent).not.toContain("Original PDF unavailable");
    expect(host.querySelectorAll('a[target="_blank"]')).toHaveLength(count);
  }
);

it.each(["page", "corpus"] as const)(
  "%s preserves a real source failure after successful document addition",
  async (surface) => {
    postAdditionError = "Original PDF is missing. Reprocess this source.";
    await render(surface);
    await addDocuments(1);
    expect(
      requests.filter((name) => name === "GetExtract").length
    ).toBeGreaterThan(1);
    expect(startButton().disabled).toBe(true);
    expect(host.textContent).toContain(postAdditionError);
  }
);

it.each(["page", "corpus"] as const)(
  "%s retains the empty-source block when document addition is rejected",
  async (surface) => {
    mutationSucceeds = false;
    await render(surface);
    await addDocuments(1);
    expect(startButton().disabled).toBe(true);
    expect(host.textContent).toContain("Add a processed document");
    expect(host.querySelectorAll('a[target="_blank"]')).toHaveLength(0);
  }
);

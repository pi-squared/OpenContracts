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

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
let client: ApolloClient<unknown>;
let requests: number;
let readinessError: string | null;
const owner = { id: "owner", slug: "owner", username: "owner" };
const documentFixture = {
  id: "document",
  title: "Indexing source",
  slug: "indexing-source",
  creator: owner,
  pdfFile: "/sample.pdf",
  fileType: "application/pdf",
  description: "Sample",
  pageCount: 1,
  processingStatus: "COMPLETED",
};
function fixture(started: string | null = null) {
  return {
    id: "extract",
    name: "Readiness refresh",
    corpus: { id: "corpus", title: "Corpus", slug: "corpus", creator: owner },
    creator: owner,
    created: "2026-10-22T00:00:00Z",
    started,
    finished: null,
    error: null,
    sourceReadinessError: readinessError,
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
    fullDocumentList: [documentFixture],
    fullDatacellList: [],
  };
}
beforeEach(() => {
  vi.useFakeTimers();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  requests = 0;
  readinessError =
    "Document retrieval index is incomplete. Wait for indexing before extracting.";
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  client?.stop();
  openedExtract(null);
  vi.useRealTimers();
});
async function render(
  surface: "page" | "corpus",
  started: string | null = null
) {
  // Route state supplies identity; the real Apollo query supplies the record.
  openedExtract({
    id: "extract",
    name: "Readiness refresh",
    created: "2026-10-22T00:00:00Z",
  } as ExtractType);
  client = new ApolloClient({
    cache: new InMemoryCache(),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          if (operation.operationName === "GetExtract") requests += 1;
          observer.next({
            data:
              operation.operationName === "GetExtract"
                ? { extract: fixture(started) }
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
function startButton() {
  const button = Array.from(host.querySelectorAll("button")).find(
    (candidate) =>
      candidate.textContent?.trim() === "Start Extract" ||
      candidate.getAttribute("aria-label") === "Start extract"
  );
  expect(button).toBeDefined();
  return button!;
}
it.each(["page", "corpus"] as const)(
  "%s enables extraction after indexing completes without manual refresh, then stops fetching",
  async (surface) => {
    await render(surface);
    expect(startButton().disabled).toBe(true);
    expect(host.textContent).toContain("Wait for indexing");
    readinessError = null;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100);
    });
    expect(startButton().disabled).toBe(false);
    expect(host.textContent).not.toContain("Wait for indexing");
    const readyRequests = requests;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(requests).toBe(readyRequests);
  }
);
it.each(["page", "corpus"] as const)(
  "%s refreshes source readiness while document processing completes",
  async (surface) => {
    readinessError =
      "Document processing is incomplete. Wait for processing before extracting.";
    await render(surface);
    expect(startButton().disabled).toBe(true);
    readinessError = null;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100);
    });
    expect(startButton().disabled).toBe(false);
    expect(host.textContent).not.toContain("Wait for processing");
  }
);
it.each(["page", "corpus"] as const)(
  "%s keeps a permanent failed source disabled without repeatedly fetching",
  async (surface) => {
    readinessError =
      "Document processing failed. Open the original PDF and reprocess the source before extracting.";
    await render(surface);
    expect(startButton().disabled).toBe(true);
    const initialRequests = requests;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(requests).toBe(initialRequests);
    expect(startButton().disabled).toBe(true);
  }
);

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
import { ExtractDataGrid } from "../src/components/extracts/datagrid/DataGrid";
import { ExtractDetailContent } from "../src/components/extracts/ExtractDetailContent";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
let client: ApolloClient<unknown>;
let requests: string[];
let fixture: ReturnType<typeof createFixture>;
const documentFixture = {
  id: "document",
  title: "Public fixture",
  fileType: "application/pdf",
  description: null,
  pageCount: 1,
};
const columns = [
  {
    id: "success",
    name: "Saved criterion",
    outputType: "str",
    extractIsList: false,
    query: null,
    instructions: null,
    matchText: null,
    limitToLabel: null,
    taskName: null,
  },
  {
    id: "failure",
    name: "Interrupted criterion",
    outputType: "str",
    extractIsList: false,
    query: null,
    instructions: null,
    matchText: null,
    limitToLabel: null,
    taskName: null,
  },
];

function nullableString(value: string | null) {
  return value;
}
function createFixture() {
  return {
    id: "extract",
    name: "Interrupted comparison",
    created: "2026-10-09T10:00:00Z",
    started: "2026-10-09T10:00:00Z",
    finished: nullableString("2026-10-09T11:00:00Z"),
    error: nullableString(
      "1 failed/interrupted criteria; original attempts retained."
    ),
    sourceReadinessError: null,
    corpus: null,
    creator: { id: "reviewer", slug: "reviewer", username: "reviewer" },
    modelConfig: null,
    iterationAxis: null,
    parentExtract: null,
    fullIterationList: [],
    fieldset: {
      id: "fieldset",
      name: "Fixture",
      inUse: true,
      fullColumnList: columns,
    },
    fullDocumentList: [documentFixture],
    fullDatacellList: [
      {
        id: "saved",
        column: columns[0],
        document: documentFixture,
        data: { data: "VALUE_A" },
        started: "2026-10-09T10:00:00Z",
        completed: "2026-10-09T10:01:00Z",
        failed: null,
        approvedBy: null,
        rejectedBy: null,
        correctedData: null,
        hasFindingEvidence: false,
        dataDefinition: null,
        stacktrace: null,
      },
      {
        id: "interrupted",
        column: columns[1],
        document: documentFixture,
        data: null,
        started: "2026-10-09T10:02:00Z",
        completed: null,
        failed: "2026-10-09T11:00:00Z",
        stacktrace:
          "Operator acknowledged an interrupted worker; failure_mode=interrupted_operator.",
        approvedBy: null,
        rejectedBy: null,
        correctedData: null,
        hasFindingEvidence: false,
        dataDefinition: null,
      },
    ],
  };
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  requests = [];
  fixture = createFixture();
  client = new ApolloClient({
    cache: new InMemoryCache({ addTypename: false }),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          requests.push(operation.operationName);
          if (operation.operationName === "GetExtract")
            observer.next({ data: { extract: fixture } });
          else if (operation.operationName === "GetDocuments")
            observer.next({
              data: {
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
          else observer.next({ data: {} });
          observer.complete();
        })
    ),
  });
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  client.stop();
  vi.restoreAllMocks();
});
async function render(view: string) {
  await act(async () => {
    root.render(
      <ApolloProvider client={client}>
        <MemoryRouter>
          {view === "grid" ? (
            <ExtractDataGrid
              extract={fixture}
              cells={fixture.fullDatacellList}
              rows={fixture.fullDocumentList}
              columns={columns}
              onAddDocIds={() => {}}
              onRemoveDocIds={() => {}}
              onRemoveColumnId={() => {}}
              onAddColumn={() => {}}
            />
          ) : view === "corpus" ? (
            <CorpusExtractDetail extractId="extract" onClose={() => {}} />
          ) : (
            <ExtractDetailContent extractId="extract" />
          )}
        </MemoryRouter>
      </ApolloProvider>
    );
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
}

it.each(["shared", "corpus"])(
  "keeps saved findings reviewable when the parent extract has errors in the %s detail",
  async (view) => {
    await render(view);
    expect(host.textContent).toContain("VALUE_A");
    expect(
      host.querySelectorAll('[aria-label="Cell status actions"]')
    ).toHaveLength(1);
    expect(
      host.querySelector(
        'button[aria-label="View failure: Interrupted criterion"]'
      )
    ).not.toBeNull();
    expect(requests).not.toContain("StartExtract");
  }
);

it("distinguishes unfinished and missing fields after a run stops", async () => {
  fixture.fullDatacellList[0].completed = null;
  fixture.fullDatacellList.pop();
  await render("shared");
  expect(host.textContent).toContain(
    "0 completed · 0 failed · 1 interrupted · 1 not reported"
  );
  expect(host.textContent).toContain("Extraction interrupted");
  expect(host.textContent).toContain("No result recorded");
  expect(host.textContent).not.toContain("Loading...");
  expect(
    host.querySelectorAll('[aria-label="Cell status actions"]')
  ).toHaveLength(0);
});

it("retains a saved failed-field value without counting it as a success", async () => {
  fixture.fullDatacellList[1].data = { data: "VALUE_B" };
  fixture.fullDatacellList[1].completed = fixture.finished;
  await render("shared");
  expect(host.textContent).toContain("VALUE_B");
  expect(host.textContent).toContain("1 completed · 1 failed");
  expect(host.textContent).toMatch(/50%\s*Success/);
  expect(
    host.querySelectorAll('[aria-label="Cell status actions"]')
  ).toHaveLength(1);
  await act(async () =>
    host
      .querySelector<HTMLButtonElement>(
        'button[aria-label="View failure: Interrupted criterion"]'
      )!
      .click()
  );
  expect(document.body.textContent).toContain("A saved value is available");
  expect(requests).not.toContain("StartExtract");
});

it("reports a failed parent honestly even when it has a finish timestamp", async () => {
  await render("corpus");
  expect(host.textContent).not.toContain("Completed");
  expect(host.textContent).toContain("Failed");
  expect(host.textContent).toContain("VALUE_A");
});

it("keeps completed results reviewable when an unfinished parent stops with errors", async () => {
  fixture.finished = null;
  await render("shared");
  expect(host.textContent).toContain("VALUE_A");
  expect(host.textContent).toContain("1 completed · 1 failed");
  expect(
    host.querySelectorAll('[aria-label="Cell status actions"]')
  ).toHaveLength(1);
});

it("distinguishes a run still processing from a terminal failure", async () => {
  fixture.error = null;
  fixture.finished = null;
  fixture.fullDatacellList[1].failed = null;
  await render("corpus");
  expect(host.textContent).toContain("Extraction in progress");
  expect(host.textContent).toContain("Running");
  expect(host.textContent).not.toContain("This run ended with errors");
  expect(
    host.querySelectorAll('[aria-label="Cell status actions"]')
  ).toHaveLength(0);
});

it("keeps every failed field inspectable when the run has no successful results", async () => {
  fixture.fullDatacellList[0].data = null;
  fixture.fullDatacellList[0].completed = null;
  fixture.fullDatacellList[0].failed = fixture.finished;
  await render("shared");
  expect(host.textContent).toContain("0 completed · 2 failed");
  expect(
    host.querySelectorAll('button[aria-label^="View failure:"]')
  ).toHaveLength(2);
  expect(
    host.querySelectorAll('[aria-label="Cell status actions"]')
  ).toHaveLength(0);
});

it("shows a pending field while its extract is still running", async () => {
  fixture.error = null;
  fixture.finished = null;
  fixture.fullDatacellList[1].failed = null;
  await render("grid");
  expect(host.textContent).toContain("Pending");
  expect(host.textContent).not.toContain("No result recorded");
  expect(
    host.querySelectorAll('button[aria-label^="View failure:"]')
  ).toHaveLength(0);
  expect(
    host.querySelectorAll('[aria-label="Cell status actions"]')
  ).toHaveLength(0);
});

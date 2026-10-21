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
import { print, visit } from "graphql";
import { afterEach, beforeEach, expect, it } from "vitest";
import { ExtractCellFormatter } from "../src/components/extracts/datagrid/ExtractCellFormatter";
import { REQUEST_GET_EXTRACT } from "../src/graphql/queries";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
let requests: Array<{
  query: string;
  variables: Record<string, unknown>;
  resolve: (data: unknown) => void;
  reject: () => void;
}>;
let client: ApolloClient<unknown>;
beforeEach(() => {
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
            query: print(operation.query),
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
});
const finding = {
  finding: "supported",
  rationale: "Signature field",
  evidence_quote: '[{"quote":"Owner signature","page":2}]',
};
function render(
  correctedData: unknown = null,
  value: unknown = finding,
  hasFindingEvidence = true,
  originalData: unknown = finding
) {
  act(() =>
    root.render(
      <ApolloProvider client={client}>
        <MemoryRouter>
          <ExtractCellFormatter
            value={value}
            cellId="cell-1"
            cell={{ id: "cell-1", hasFindingEvidence } as any}
            cellStatus={{
              isLoading: false,
              isApproved: true,
              isRejected: false,
              isEdited: correctedData !== null,
              correctedData,
              originalData,
              error: null,
            }}
            onApprove={() => {}}
            onReject={() => {}}
            onEdit={() => {}}
            readOnly={true}
            isExtractComplete={true}
            schema={{}}
            extractIsList={false}
            row={{}}
            column={{ name: "Agreement signature" }}
          />
        </MemoryRouter>
      </ApolloProvider>
    )
  );
}
function click(label: string) {
  const button = Array.from(
    document.body.querySelectorAll("button,[role=button]")
  ).find(
    (item) =>
      item.getAttribute("aria-label") === label || item.textContent === label
  );
  expect(button).toBeDefined();
  act(() => (button as HTMLElement).click());
}
it("the native grid request carries availability without resolving quotation projections", () => {
  const fields: string[] = [];
  visit(REQUEST_GET_EXTRACT, {
    Field(node) {
      fields.push(node.name.value);
    },
  });
  expect(fields).not.toContain("fullSourceList");
  expect(fields).not.toContain("findingEvidence");
  expect(fields).toContain("hasFindingEvidence");
});
it("requests one cell's evidence only after opening details and reports loading then parsed text locations", async () => {
  render();
  expect(requests).toHaveLength(0);
  click("View finding: Supported");
  expect(requests).toHaveLength(1);
  expect(requests[0].variables).toEqual({ id: "cell-1", version: "effective" });
  expect(requests[0].query).toContain("datacell(id: $id)");
  expect(document.body.textContent).toContain("Loading quotation locations");
  expect(
    document.body.querySelector('button[aria-label="View quotation in PDF"]')
  ).toBeNull();
  await act(async () =>
    requests[0].resolve({
      datacell: {
        id: "cell-1",
        findingEvidence: [
          {
            quote: "Owner signature",
            reportedPage: 2,
            locatedPage: 3,
            status: "different_page",
            annotationId: "quote-1",
          },
        ],
        fullSourceList: [],
      },
    })
  );
  expect(document.body.textContent).toContain(
    "Matched in parsed text on PDF page 3"
  );
  expect(document.body.textContent).toContain("Review: Approved");
});
it("keeps failed source loading distinct from no evidence and retries through the public node", async () => {
  render();
  click("View finding: Supported");
  await act(async () => requests[0].reject());
  expect(document.body.textContent).toContain(
    "Quotation locations could not be loaded"
  );
  expect(document.body.textContent).not.toContain("No quotations recorded");
  click("Retry quotation locations");
  expect(requests).toHaveLength(2);
  await act(async () =>
    requests[1].resolve({
      datacell: { id: "cell-1", findingEvidence: [], fullSourceList: [] },
    })
  );
  expect(document.body.textContent).toContain("No quotations recorded");
  expect(document.body.textContent).not.toContain("could not be loaded");
});
it("discarding an in-flight original request cannot attach its quotes to a corrected finding", async () => {
  render();
  click("View finding: Supported");
  const original = requests[0];
  click("Close");
  render({
    data: {
      ...finding,
      rationale: "Corrected assessment",
      evidence_quote: '[{"quote":"Corrected quote","page":4}]',
    },
  });
  click("View finding: Supported");
  expect(requests).toHaveLength(2);
  await act(async () =>
    original.resolve({
      datacell: {
        id: "cell-1",
        findingEvidence: [
          {
            quote: "Old quote",
            reportedPage: 2,
            locatedPage: 2,
            status: "matched",
            annotationId: "old",
          },
        ],
        fullSourceList: [],
      },
    })
  );
  expect(document.body.textContent).not.toContain("Old quote");
  expect(document.body.textContent).toContain("Loading quotation locations");
  await act(async () =>
    requests[1].resolve({
      datacell: {
        id: "cell-1",
        findingEvidence: [
          {
            quote: "Corrected quote",
            reportedPage: 4,
            locatedPage: 4,
            status: "matched",
            annotationId: "new",
          },
        ],
        fullSourceList: [],
      },
    })
  );
  expect(document.body.textContent).toContain("Corrected quote");
  expect(document.body.textContent).toContain("Corrected assessment");
});
it("an open finding refreshes its quotation locations after a correction", async () => {
  render();
  click("View finding: Supported");
  await act(async () =>
    requests[0].resolve({
      datacell: {
        id: "cell-1",
        findingEvidence: [
          {
            quote: "Old quote",
            reportedPage: 2,
            locatedPage: 2,
            status: "matched",
            annotationId: "old",
          },
        ],
        fullSourceList: [],
      },
    })
  );
  render({
    data: {
      ...finding,
      rationale: "Corrected assessment",
      evidence_quote: '[{"quote":"Revised quote","page":4}]',
    },
  });
  expect(requests).toHaveLength(2);
  expect(document.body.textContent).toContain("Loading quotation locations");
  expect(document.body.textContent).not.toContain("Old quote");
  await act(async () =>
    requests[1].resolve({
      datacell: {
        id: "cell-1",
        findingEvidence: [
          {
            quote: "Revised quote",
            reportedPage: 4,
            locatedPage: 4,
            status: "matched",
            annotationId: "revised",
          },
        ],
        fullSourceList: [],
      },
    })
  );
  expect(document.body.textContent).toContain("Revised quote");
});

it("stock primitive cells inspect sources on demand without requiring a finding quote", async () => {
  render(null, 123, false);
  expect(requests).toHaveLength(0);
  click("Cell status actions");
  click("View Sources");
  expect(requests).toHaveLength(1);
  expect(document.body.textContent).toContain("Loading source locations");
  await act(async () =>
    requests[0].resolve({
      datacell: { id: "cell-1", findingEvidence: [], fullSourceList: [] },
    })
  );
  expect(document.body.textContent).toContain(
    "No highlighted source available"
  );
});

it("inspects an original not_found under its own rules while its correction is supported", () => {
  render(finding, finding, true, {
    ...finding,
    finding: "not_found",
    rationale: "Original rationale",
  });
  click("Cell status actions");
  click("View original");
  expect(requests).toHaveLength(0);
  expect(document.body.textContent).toContain("Original rationale");
  expect(document.body.textContent).not.toContain("Owner signature");
  expect(document.body.textContent).not.toContain("No quotations recorded");
});

it("a late eligible response cannot restore evidence after correction to not_found", async () => {
  render();
  click("View finding: Supported");
  const previous = requests[0];
  render({
    ...finding,
    finding: "not_found",
    rationale: "Corrected rationale",
  });
  expect(requests).toHaveLength(1);
  await act(async () =>
    previous.resolve({
      datacell: {
        id: "cell-1",
        findingEvidence: [
          { quote: "Obsolete selected quote", annotationId: "old" },
        ],
        fullSourceList: [],
      },
    })
  );
  expect(document.body.textContent).toContain("Corrected rationale");
  expect(document.body.textContent).not.toContain("Obsolete selected quote");
  expect(document.body.textContent).not.toContain("Owner signature");
  expect(document.body.textContent).not.toContain("No quotations recorded");
});

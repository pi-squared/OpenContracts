import { fireEvent } from "@testing-library/react";
import { visit } from "graphql";
import React, { act, createRef } from "react";
import { createRoot, Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  InMemoryCache,
  Observable,
} from "@apollo/client";
import { unzipSync, strFromU8 } from "fflate";
import { csvParse } from "d3-dsv";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  ExtractDataGrid,
  ExtractDataGridHandle,
} from "../src/components/extracts/datagrid/DataGrid";
import { REQUEST_GET_EXTRACT } from "../src/graphql/queries";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
let client: ApolloClient<unknown>;
let downloads: Blob[];
let requests: string[];
let savedCell: any;
let refreshEvidenceAvailability = false;
const originalCreate = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
const originalRevoke = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
const grid = createRef<ExtractDataGridHandle>();
const finding = {
  finding: "supported",
  rationale: "Two selected passages were saved.",
  evidence: [
    { quote: "First saved passage", page: 1 },
    { quote: "Retained saved passage", page: 2 },
  ],
};
const column = {
  id: "criterion",
  name: "Criterion",
  outputType: "dict",
  extractIsList: false,
};
const fixtureDocument = {
  id: "document",
  title: "Fixture agreement",
  fileType: "application/pdf",
};
const extract = {
  id: "extract",
  name: "Fixture",
  started: "2026-10-05T10:00:00Z",
  finished: "2026-10-05T10:01:00Z",
  error: null,
};
function cell(
  data: unknown = { data: finding },
  correctedData: unknown = null
) {
  return {
    __typename: "DatacellType",
    id: "cell",
    data,
    correctedData,
    column,
    document: fixtureDocument,
    started: extract.started,
    completed: extract.finished,
    failed: null,
    stacktrace: null,
    approvedBy: null,
    rejectedBy: null,
    findingEvidence: [],
    fullSourceList: [],
    hasFindingEvidence: false,
  };
}
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  downloads = [];
  requests = [];
  savedCell = cell();
  refreshEvidenceAvailability = false;
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: (blob: Blob) => {
      downloads.push(blob);
      return "blob:fixture-download";
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: () => {},
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  client = new ApolloClient({
    cache: new InMemoryCache(),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          requests.push(operation.operationName);
          if (operation.operationName === "EditDatacell") {
            savedCell = {
              ...savedCell,
              correctedData: operation.variables.editedData,
            };
            const returned = { ...savedCell };
            if (refreshEvidenceAvailability) {
              savedCell.hasFindingEvidence = operation.variables.editedData.finding !== "not_found";
              const fields: string[] = [];
              visit(operation.query, { Field(node) { fields.push(node.name.value); } });
              if (fields.includes("hasFindingEvidence")) returned.hasFindingEvidence = savedCell.hasFindingEvidence;
              else delete returned.hasFindingEvidence;
            }
            observer.next({
              data: {
                editDatacell: { ok: true, message: "Saved", obj: returned },
              },
            });
          } else if (operation.operationName === "GetDatacellEvidence") {
            expect(operation.variables.version).toBe(refreshEvidenceAvailability ? "effective" : "original");
            observer.next({
              data: {
                datacell: {
                  id: savedCell.id,
                  findingEvidence: finding.evidence.map((entry) => ({
                    ...entry,
                    reportedPage: entry.page,
                    locatedPage: entry.page,
                    status: "matched",
                  })),
                  fullSourceList: [],
                },
              },
            });
          } else if (operation.operationName === "GetExtract") {
            observer.next({
              data: {
                extract: { ...extract, fullDatacellList: [{ ...savedCell }] },
              },
            });
          } else if (operation.operationName === "GetDocuments") {
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
          } else observer.next({ data: {} });
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
  for (const [name, descriptor] of [
    ["createObjectURL", originalCreate],
    ["revokeObjectURL", originalRevoke],
  ] as const) {
    if (descriptor) Object.defineProperty(URL, name, descriptor);
    else Reflect.deleteProperty(URL, name);
  }
});
function render(cells = [savedCell]) {
  act(() =>
    root.render(
      <ApolloProvider client={client}>
        <MemoryRouter>
          <button onClick={() => grid.current?.exportToCsv()}>
            Download CSV
          </button>
          <button onClick={() => grid.current?.exportToExcel()}>
            Download Excel
          </button>
          <ExtractDataGrid
            ref={grid}
            extract={extract as any}
            cells={cells}
            rows={[fixtureDocument as any]}
            columns={[column as any]}
            onAddDocIds={() => {}}
            onRemoveDocIds={() => {}}
            onRemoveColumnId={() => {}}
            onAddColumn={() => {}}
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
async function exportedValue() {
  click("Download CSV");
  const blob = downloads.at(-1)!;
  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsText(blob);
  });
  return csvParse(content)[0].Criterion;
}

it("exports a saved native quote removal immediately and after the persisted cell is requeried", async () => {
  const initialCell = savedCell;
  render([initialCell]);
  click("Cell status actions");
  click("Edit");
  const key = Array.from(document.body.querySelectorAll(".array-key")).find(
    (element) => element.textContent === "0"
  );
  expect(key).toBeDefined();
  act(() => key!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
  const entry = key!.closest(".object-key-val")!;
  const remove = entry.querySelector(
    ":scope > span > .object-meta-data .click-to-remove-icon"
  );
  expect(remove).not.toBeNull();
  await act(async () => {
    (remove as HTMLElement).click();
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  expect(requests).toContain("EditDatacell");
  expect(savedCell.correctedData.evidence).toEqual([
    { quote: "Retained saved passage", page: 2 },
  ]);
  expect(initialCell.data.data.evidence).toHaveLength(2);
  click("Close");
  expect(JSON.parse(await exportedValue()).evidence).toEqual([
    { quote: "Retained saved passage", page: 2 },
  ]);

  const response = await client.query({
    query: REQUEST_GET_EXTRACT,
    variables: { id: extract.id },
    fetchPolicy: "no-cache",
  });
  render(response.data.extract.fullDatacellList);
  expect(requests).toContain("GetExtract");
  expect(JSON.parse(await exportedValue()).evidence).toEqual([
    { quote: "Retained saved passage", page: 2 },
  ]);
});

it("offers readable original inspection after correction without editing the saved JSON", async () => {
  render();
  expect(host.querySelector('button[aria-label="View original"]')).toBeNull();
  savedCell = cell(
    { data: finding },
    {
      ...finding,
      rationale: "The corrected finding retains one selected passage.",
      evidence: [{ quote: "Retained saved passage", page: 2 }],
    }
  );
  render([savedCell]);
  await act(async () => click("View original"));
  const dialog = document.body.querySelector('[role="dialog"]');
  expect(dialog?.textContent).toContain("Original Value");
  expect(dialog?.textContent).toContain("First saved passage");
  expect(dialog?.textContent).toContain("Retained saved passage");
  expect(
    dialog?.querySelectorAll(".edit-icon, .object-add, .object-remove").length
  ).toBe(0);
  click("Close");
  expect(host.textContent).toContain(
    "The corrected finding retains one selected passage."
  );
  expect(host.textContent).not.toContain("First saved passage");
});

it("exports no selected evidence for a retained not_found correction while preserving the original", async () => {
  savedCell = cell({ data: finding }, { ...finding, finding: "not_found" });
  render([savedCell]);
  const exported = await exportedValue();
  expect(exported).not.toContain("First saved passage");
  expect(exported).not.toContain("Retained saved passage");
  expect(JSON.parse(exported).finding).toBe("not_found");
  await act(async () => click("View original"));
  expect(document.body.textContent).toContain("First saved passage");
  expect(savedCell.correctedData.evidence).toEqual(finding.evidence);
  expect(savedCell.data.data).toEqual(finding);
  click("Close");
});

it.each([
  ["wrapped original zero", { data: 0 }, null, "0"],
  ["wrapped original false", { data: false }, null, "false"],
  ["plain original zero", 0, null, "0"],
  ["plain original string", "Saved text", null, "Saved text"],
  ["original array", { data: ["one", "two"] }, null, '["one","two"]'],
  [
    "original single-field object",
    { data: { amount: 1 } },
    null,
    '{"amount":1}',
  ],
  ["nested original payload", { data: { data: 0 } }, null, '{"data":0}'],
  ["plain corrected zero", { data: 9 }, 0, "0"],
  ["plain corrected false", { data: true }, false, "false"],
  ["plain corrected string", { data: "Original" }, "Corrected", "Corrected"],
  ["wrapped corrected zero", { data: 9 }, { data: 0 }, "0"],
  ["wrapped corrected false", { data: true }, { data: false }, "false"],
  [
    "wrapped corrected array",
    { data: ["original"] },
    { data: ["retained"] },
    '["retained"]',
  ],
  ["corrected object", { data: { amount: 9 } }, { amount: 0 }, '{"amount":0}'],
  ["corrected empty object", { data: "Original" }, {}, "{}"],
  ["corrected empty array", { data: "Original" }, [], "[]"],
  ["corrected empty string", { data: "Original" }, "", ""],
  ["wrapped corrected null", { data: "Original" }, { data: null }, ""],
  ["quoted scalar", { data: "Original" }, 'Said "yes"', 'Said "yes"'],
  [
    "multiline scalar",
    { data: "Original" },
    'Said "yes"\nthen, no',
    'Said "yes"\nthen, no',
  ],
])(
  "exports %s through native CSV without dropping or changing its value",
  async (_name, original, corrected, expected) => {
    savedCell = cell(original, corrected);
    render([savedCell]);
    expect(await exportedValue()).toBe(expected);
    expect(
      Boolean(host.querySelector('button[aria-label="View original"]'))
    ).toBe(corrected != null);
  }
);

// A finished parent can contain a failed field; it must remain distinguishable.
it("shows a failed field with context and keeps successful fields reviewable", () => {
  render([{ ...cell(null), completed: null, failed: "2026-10-05T10:01:00Z" }]);
  expect(host.textContent).toContain("Extraction failed");
  click("View failure: Criterion");
  expect(document.body.textContent).toContain("No finding was produced");
  expect(document.body.textContent).toContain("Iterations");
  expect(
    document.body.querySelector('[aria-label="Cell status actions"]')
  ).toBeNull();
});

it("downloads an Excel workbook with the document title and current reviewer value", async () => {
  render([cell({ data: finding }, "Reviewer correction")]);
  click("Download Excel");
  const blob = downloads.at(-1)!;
  expect(blob.type).toBe(
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  );
  const bytes = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = reject;
    reader.readAsArrayBuffer(blob);
  });
  const files = unzipSync(new Uint8Array(bytes));
  const sheet = new DOMParser().parseFromString(
    strFromU8(files["xl/worksheets/sheet1.xml"]),
    "application/xml"
  );
  expect(
    sheet.documentElement.nodeName,
    sheet.documentElement.textContent || ""
  ).not.toBe("parsererror");
  expect(
    Array.from(sheet.getElementsByTagName("t")).map((node) => node.textContent)
  ).toEqual([
    "Document",
    "Criterion",
    "Fixture agreement",
    "Reviewer correction",
  ]);
});


it("reloads PDF locations after a native correction restores selected evidence", async () => {
  refreshEvidenceAvailability = true;
  savedCell = cell({ data: { ...finding, finding: "not_found" } });
  render([savedCell]);
  click("View finding: Not found");
  click("Edit data");
  const value = Array.from(document.body.querySelectorAll(".variable-value")).find(
    (node) => node.textContent?.includes("not_found")
  );
  expect(value).toBeDefined();
  act(() => fireEvent.click(value!, { ctrlKey: true }));
  const input = document.body.querySelector('[placeholder="update this value"]');
  expect(input).not.toBeNull();
  act(() => fireEvent.change(input!, { target: { value: "supported" } }));
  await act(async () => {
    fireEvent.click(document.body.querySelector(".edit-check")!);
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  click("Close");
  await act(async () => click("View finding: Supported"));
  expect(requests).toContain("GetDatacellEvidence");
  expect(document.body.querySelector('[role="dialog"]')?.textContent).toContain(
    "Matched in parsed text on PDF page 2."
  );
});

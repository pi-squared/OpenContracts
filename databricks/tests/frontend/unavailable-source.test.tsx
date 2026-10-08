import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { ExtractDataGrid } from "../src/components/extracts/datagrid/DataGrid";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

it("a failed source keeps original PDF access without locating or rewriting findings", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const sourceDocument = {
    id: "document",
    title: "Failed agreement",
    slug: "failed-agreement",
    creator: { id: "owner", slug: "owner" },
    fileType: "application/pdf",
    extractionReadinessError:
      "Document processing failed. Reprocess the source before extracting.",
  };
  const column = { id: "criterion", name: "Criterion", outputType: "str" };
  try {
    await act(async () =>
      root.render(
        <MockedProvider>
          <MemoryRouter>
            <ExtractDataGrid
              extract={
                {
                  id: "extract",
                  name: "Old run",
                  sourceReadinessError: "Document processing failed.",
                  started: "2026-10-08",
                  finished: "2026-10-08",
                } as any
              }
              rows={[sourceDocument] as any}
              columns={[column] as any}
              cells={
                [
                  {
                    id: "cell",
                    document: sourceDocument,
                    column,
                    data: {
                      data: {
                        finding: "supported",
                        rationale: "Kept",
                        evidence: [],
                      },
                    },
                    completed: "2026-10-08",
                    hasFindingEvidence: false,
                    fullSourceList: [],
                  },
                ] as any
              }
              onAddDocIds={() => {}}
              onRemoveDocIds={() => {}}
              onRemoveColumnId={() => {}}
              onAddColumn={() => {}}
            />
          </MemoryRouter>
        </MockedProvider>
      )
    );
    expect(host.querySelector('[role="alert"]')?.textContent).toContain(
      "Existing findings are unreliable"
    );
    const original = Array.from(host.querySelectorAll("a")).find(
      (a) => a.textContent === "Open original PDF"
    );
    expect(original?.getAttribute("href")).toBe("/d/owner/failed-agreement");
    expect(
      host.querySelector('[aria-label="View finding: Supported"]')
    ).not.toBeNull();
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

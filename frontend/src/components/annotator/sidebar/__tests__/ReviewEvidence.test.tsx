import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SingleDocumentExtractResults } from "../SingleDocumentExtractResults";
import { DatacellType, ColumnType } from "../../../../types/graphql-api";
import { REQUEST_EDIT_DATACELL } from "../../../../graphql/mutations";

const manager = vi.hoisted(() => ({ cells: [] as unknown[] }));
vi.mock("../../hooks/AnalysisHooks", () => ({
  useAnalysisManager: () => ({
    dataCells: manager.cells,
    setDataCells: vi.fn(),
    extractResultsLoading: false,
    extractResultsError: undefined,
    retryExtractResults: vi.fn(),
  }),
}));
vi.mock("../../../../hooks/useEvidenceFocus", () => ({
  useEvidenceFocus: () => ({
    focusedEvidenceId: null,
    focusRequest: 0,
    setFocusedEvidence: vi.fn(),
    navigateToEvidence: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  manager.cells = [];
});

const field = { id: "column-apr", name: "Annual percentage rate disclosure" };
const response = {
  data: {
    finding: "present_blank",
    evidence: [
      { quote: "14. APR", page: 5 },
      { quote: "%", page: 5 },
    ],
    rationale: "The APR field is blank.",
  },
};
const corrected = {
  ...response,
  reviewer_feedback: {
    verdict_comment: "Preserved verdict comment",
    evidence_comment: "Preserved evidence comment",
  },
};
const matched = {
  quote: "14. APR",
  reportedPage: 5,
  locatedPage: 5,
  selectionPath: "/evidence/0",
  status: "matched",
  annotationId: "annotation798",
};
const ambiguous = {
  quote: "%",
  reportedPage: 5,
  locatedPage: null,
  selectionPath: "/evidence/1",
  status: "ambiguous",
  annotationId: null,
};

function cell(overrides: Record<string, unknown> = {}): DatacellType {
  return {
    id: "cell7",
    column: field,
    data: response,
    correctedData: corrected,
    fullSourceList: [
      { id: "annotation798", annotationLabel: { text: field.name } },
    ],
    findingEvidence: [matched, ambiguous],
    ...overrides,
  } as unknown as DatacellType;
}

function results(cells = [cell()]) {
  return render(
    <MockedProvider>
      <MemoryRouter>
        <SingleDocumentExtractResults
          datacells={cells}
          columns={[field as ColumnType]}
        />
      </MemoryRouter>
    </MockedProvider>
  );
}

function openEvidence() {
  fireEvent.click(screen.getByRole("button", { name: "Edit finding" }));
  fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
  return within(screen.getByRole("dialog", { name: "Review extraction" }));
}

describe("selected finding evidence in review", () => {
  it("explains the exact APR two-quote/one-highlight discrepancy and keeps both quotations", () => {
    results();
    expect(
      screen.getByRole("button", { name: "1 Annotation" })
    ).toBeInTheDocument();
    const review = openEvidence();
    expect(review.getByText("14. APR", { exact: true })).toBeInTheDocument();
    expect(review.getByText("%", { exact: true })).toBeInTheDocument();
    expect(
      review.getByText("Matched in parsed text on PDF page 5.")
    ).toBeInTheDocument();
    expect(
      review.getByText("Multiple possible source locations. No highlight.")
    ).toBeInTheDocument();
    expect(review.getByLabelText("Evidence comment")).toHaveValue(
      "Preserved evidence comment"
    );
    expect(
      review.getAllByRole("button", { name: /Reject quotation/ })
    ).toHaveLength(2);
    fireEvent.click(review.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByRole("dialog", { name: "Review extraction" })
    ).not.toBeInTheDocument();
    openEvidence().getByText(
      "Multiple possible source locations. No highlight."
    );
    expect(response.data.evidence).toHaveLength(2);
  });

  it("uses each quotation's selection path when repeated text has different grounding", () => {
    results([
      cell({
        correctedData: {
          data: {
            ...response.data,
            evidence: [
              { quote: "%", page: 5 },
              { quote: "%", page: 5 },
            ],
          },
        },
        findingEvidence: [
          { ...ambiguous, selectionPath: "/evidence/0" },
          { ...matched, quote: "%", selectionPath: "/evidence/1" },
        ],
      }),
    ]);
    const review = openEvidence();
    const entries = review.getAllByRole("article");
    expect(
      within(entries[0]).getByText(
        "Multiple possible source locations. No highlight."
      )
    ).toBeInTheDocument();
    expect(
      within(entries[1]).getByText("Matched in parsed text on PDF page 5.")
    ).toBeInTheDocument();
  });

  it.each([
    { ...ambiguous, quote: "different finding" },
    { ...ambiguous, reportedPage: 17 },
    { ...ambiguous, selectionPath: "/evidence/0" },
  ])(
    "does not attach stale or unrelated grounding to the percent quotation: %j",
    (anchor) => {
      results([cell({ findingEvidence: [matched, anchor] })]);
      const review = openEvidence();
      const percent = review.getAllByRole("article")[1];
      expect(
        within(percent).queryByText(
          "Multiple possible source locations. No highlight."
        )
      ).not.toBeInTheDocument();
      expect(
        within(percent).getByText(
          "Retained source location unavailable. No highlight."
        )
      ).toBeInTheDocument();
    }
  );

  it("keeps encoded legacy evidence associated with its actual source field", () => {
    results([
      cell({
        correctedData: {
          data: {
            finding: "supported",
            evidence_quote: JSON.stringify([{ quote: "Legacy", page: 6 }]),
          },
        },
        findingEvidence: [
          {
            quote: "Legacy",
            reportedPage: 6,
            locatedPage: 6,
            selectionPath: "/evidence_quote/0",
            status: "matched",
          },
        ],
      }),
    ]);
    expect(
      openEvidence().getByText("Matched in parsed text on PDF page 6.")
    ).toBeInTheDocument();
  });

  it("never treats an ambiguous quotation as located even if stray coordinates exist", () => {
    results([
      cell({
        findingEvidence: [
          matched,
          { ...ambiguous, locatedPage: 5, annotationId: "unrelated" },
        ],
      }),
    ]);
    const percent = openEvidence().getAllByRole("article")[1];
    expect(
      within(percent).getByText(
        "Multiple possible source locations. No highlight."
      )
    ).toBeInTheDocument();
    expect(
      within(percent).queryByText("Matched in parsed text on PDF page 5.")
    ).not.toBeInTheDocument();
  });

  it.each([
    "/document?findingVersion=original&findingCell=cell7",
    "/other-document",
    "/document?extract=other-extract",
  ])(
    "closes the old review when the selected document/extract/version changes to %s",
    async (target) => {
      function ContextChange() {
        const navigate = useNavigate();
        return (
          <button onClick={() => navigate(target)}>
            Change inspection context
          </button>
        );
      }
      render(
        <MockedProvider>
          <MemoryRouter initialEntries={["/document"]}>
            <ContextChange />
            <SingleDocumentExtractResults
              datacells={[cell()]}
              columns={[field as ColumnType]}
            />
          </MemoryRouter>
        </MockedProvider>
      );
      openEvidence();
      fireEvent.click(
        screen.getByRole("button", { name: "Change inspection context" })
      );
      await waitFor(() =>
        expect(
          screen.queryByRole("dialog", { name: "Review extraction" })
        ).not.toBeInTheDocument()
      );
      if (target.includes("findingVersion=original"))
        expect(
          screen.getByRole("button", { name: "Edit finding" })
        ).toBeDisabled();
    }
  );

  it("saving review comments preserves original and corrected quotations without persisting presentation metadata", async () => {
    const editedData = {
      ...corrected,
      reviewer_feedback: {
        ...corrected.reviewer_feedback,
        evidence_comment: "Additional review comment",
      },
    };
    const completed = vi.fn(() => ({
      data: {
        editDatacell: {
          ok: true,
          message: "Saved",
          obj: {
            id: "cell7",
            data: response,
            correctedData: editedData,
            started: null,
            completed: null,
            stacktrace: null,
            hasFindingEvidence: true,
            findingEvidence: [matched, ambiguous],
            column: field,
            document: {
              id: "doc5",
              title: "Synthetic agreement",
              fileType: "application/pdf",
            },
            fullSourceList: [],
          },
        },
      },
    }));
    render(
      <MockedProvider
        mocks={[
          {
            request: {
              query: REQUEST_EDIT_DATACELL,
              variables: { datacellId: "cell7", editedData },
            },
            result: completed,
          },
        ]}
      >
        <MemoryRouter>
          <SingleDocumentExtractResults
            datacells={[cell()]}
            columns={[field as ColumnType]}
          />
        </MemoryRouter>
      </MockedProvider>
    );
    const review = openEvidence();
    fireEvent.change(review.getByLabelText("Evidence comment"), {
      target: { value: "Additional review comment" },
    });
    fireEvent.click(review.getByRole("button", { name: "Save comments" }));
    await waitFor(() => expect(completed).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Review extraction" })
      ).not.toBeInTheDocument()
    );
    expect(response.data.evidence).toEqual([
      { quote: "14. APR", page: 5 },
      { quote: "%", page: 5 },
    ]);
    expect(corrected.data).toBe(response.data);
  });

  it("does not inherit a previous finding's evidence or comments after closing and selecting another", () => {
    const other = { id: "column-fees", name: "Fees and charges" };
    const second = cell({
      id: "cell8",
      column: other,
      correctedData: null,
      data: {
        data: { finding: "supported", evidence: [{ quote: "Fee", page: 6 }] },
      },
      fullSourceList: [],
      findingEvidence: [
        {
          quote: "Fee",
          reportedPage: 6,
          selectionPath: "/evidence/0",
          status: "unmatched",
        },
      ],
    });
    render(
      <MockedProvider>
        <MemoryRouter>
          <SingleDocumentExtractResults
            datacells={[cell(), second]}
            columns={[field as ColumnType, other as ColumnType]}
          />
        </MemoryRouter>
      </MockedProvider>
    );
    const first = screen.getAllByRole("button", { name: "Edit finding" })[0];
    fireEvent.click(first);
    fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Edit finding" })[1]);
    fireEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    const review = within(
      screen.getByRole("dialog", { name: "Review extraction" })
    );
    expect(review.getByText("Fee", { exact: true })).toBeInTheDocument();
    expect(
      review.getByText("Quotation not found in retained source. No highlight.")
    ).toBeInTheDocument();
    expect(
      review.queryByText("14. APR", { exact: true })
    ).not.toBeInTheDocument();
    expect(review.getByLabelText("Evidence comment")).toHaveValue("");
  });
});

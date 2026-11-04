import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { print } from "graphql";
import { GET_DOCUMENTS_FOR_LIST } from "../../graphql/queries";
import {
  DocumentProcessingStatus,
  DocumentType,
} from "../../types/graphql-api";
import { DocumentsGridView } from "../DocumentsGridView";
import { DocumentsListView } from "../DocumentsListView";
import { DocumentsCompactView } from "../DocumentsCompactView";

afterEach(cleanup);

const document = (
  processingStatus: DocumentProcessingStatus | undefined,
  backendLock: boolean
): DocumentType => ({
  id: "terminal-status-document",
  title: "Example agreement",
  fileType: "application/pdf",
  created: "2026-01-01T12:00:00Z",
  creator: { id: "example-user", email: "owner@example.test" },
  processingStatus,
  processingError: "A required processing component is unavailable.",
  backendLock,
});

const props = {
  selectedIds: [],
  allSelected: false,
  onDocumentClick: () => {},
  onSelect: () => {},
  onSelectAll: () => {},
  onContextMenu: () => {},
};

describe("library terminal processing failures", () => {
  it("requests the terminal state and cause in the actual slim list query", () => {
    const query = print(GET_DOCUMENTS_FOR_LIST);
    expect(query).toContain("processingStatus");
    expect(query).toContain("processingError");
  });

  it("gives a useful configuration message without backend paths or tracebacks", () => {
    const failed = document(DocumentProcessingStatus.FAILED, true);
    failed.processingError =
      "[E050] Can't find model '/private/server/model'. Traceback: internal details";
    render(<DocumentsGridView {...props} documents={[failed]} />);
    expect(
      screen.getByText(/required processing component is unavailable/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/private\/server|Traceback/)).toBeNull();
  });

  it("provides an actionable fallback when a failed record has no cause", () => {
    const failed = document(DocumentProcessingStatus.FAILED, false);
    failed.processingError = "";
    render(<DocumentsListView {...props} documents={[failed]} />);
    expect(
      screen.getByText(/contact an administrator before retrying/i)
    ).toBeInTheDocument();
  });

  for (const [name, View] of [
    ["grid", DocumentsGridView],
    ["list", DocumentsListView],
    ["compact", DocumentsCompactView],
  ] as const) {
    for (const locked of [true, false]) {
      it(`${name} presents a failed document as terminal with lock=${locked}`, () => {
        render(
          <View
            {...props}
            documents={[document(DocumentProcessingStatus.FAILED, locked)]}
          />
        );
        expect(screen.getByText("Processing failed")).toBeInTheDocument();
        expect(
          screen.getByText(/contact an administrator/i)
        ).toBeInTheDocument();
        expect(screen.queryByText(/^Processing(?:\.\.\.)?$/)).toBeNull();
        expect(screen.queryByText("Processed")).toBeNull();
        expect(screen.getByTestId("document-card")).toHaveAttribute(
          "data-processing",
          "false"
        );
      });
    }

    it(`${name} preserves an active processing document`, () => {
      render(
        <View
          {...props}
          documents={[document(DocumentProcessingStatus.PROCESSING, true)]}
        />
      );
      expect(screen.getByText(/^Processing(?:\.\.\.)?$/)).toBeInTheDocument();
      expect(screen.queryByText("Processing failed")).toBeNull();
      expect(screen.getByTestId("document-card")).toHaveAttribute(
        "data-processing",
        "true"
      );
    });

    it(`${name} preserves a completed and a legacy unlocked document`, () => {
      const { rerender } = render(
        <View
          {...props}
          documents={[document(DocumentProcessingStatus.COMPLETED, false)]}
        />
      );
      expect(screen.getByTestId("document-card")).toHaveAttribute(
        "data-processing",
        "false"
      );
      expect(screen.queryByText("Processing failed")).toBeNull();
      rerender(<View {...props} documents={[document(undefined, false)]} />);
      expect(screen.getByTestId("document-card")).toHaveAttribute(
        "data-processing",
        "false"
      );
    });
  }
});

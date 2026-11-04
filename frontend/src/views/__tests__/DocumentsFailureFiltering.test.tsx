import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DocumentsTestWrapper } from "../../../tests/DocumentsTestWrapper";
import {
  GET_DOCUMENTS_FOR_LIST,
  GET_DOCUMENT_STATS,
} from "../../graphql/queries";
import {
  DocumentProcessingStatus,
  DocumentType,
} from "../../types/graphql-api";

vi.mock("../../hooks/useAuthenticated", () => ({
  useAuthenticated: () => true,
}));
afterEach(cleanup);

it("keeps terminal failures out of both progress tabs in the actual library", async () => {
  const row = (
    id: string,
    status: DocumentProcessingStatus,
    locked: boolean
  ): DocumentType => ({
    id,
    slug: id,
    title: id,
    fileType: "application/pdf",
    backendLock: locked,
    processingStatus: status,
    processingError: "Processing component unavailable",
    pageCount: 1,
    icon: "",
    created: "2026-01-01T12:00:00Z",
    creator: {
      id: "example-owner",
      slug: "example-owner",
      email: "owner@example.test",
    },
  });
  const documents = [
    row("Failed locked", DocumentProcessingStatus.FAILED, true),
    row("Failed unlocked", DocumentProcessingStatus.FAILED, false),
    row("Active upload", DocumentProcessingStatus.PROCESSING, true),
    row("Completed upload", DocumentProcessingStatus.COMPLETED, false),
  ];
  render(
    <DocumentsTestWrapper
      mocks={[
        {
          request: { query: GET_DOCUMENTS_FOR_LIST, variables: { limit: 20 } },
          result: {
            data: {
              documents: {
                edges: documents.map((node) => ({ node })),
                pageInfo: {
                  hasNextPage: false,
                  hasPreviousPage: false,
                  startCursor: null,
                  endCursor: null,
                },
              },
            },
          },
        },
        {
          request: { query: GET_DOCUMENT_STATS, variables: {} },
          result: {
            data: {
              documentStats: {
                totalDocs: 4,
                totalPages: 4,
                processingCount: 1,
                processedCount: 1,
              },
            },
          },
        },
      ]}
    />
  );
  await screen.findByText("Failed locked");
  expect(screen.getAllByTestId("document-card")).toHaveLength(4);
  fireEvent.click(screen.getByRole("tab", { name: /Processing/ }));
  expect(screen.getAllByTestId("document-card")).toHaveLength(1);
  expect(screen.getByText("Active upload")).toBeInTheDocument();
  expect(screen.queryByText("Failed locked")).toBeNull();
  expect(screen.queryByText("Failed unlocked")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: /Processed/ }));
  expect(screen.getAllByTestId("document-card")).toHaveLength(1);
  expect(screen.getByText("Completed upload")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: /All Documents/ }));
  expect(screen.getAllByTestId("document-card")).toHaveLength(4);
  expect(screen.getAllByText("Processing failed")).toHaveLength(2);
});

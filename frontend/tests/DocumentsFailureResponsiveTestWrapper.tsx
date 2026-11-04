import React from "react";
import {
  DocumentProcessingStatus,
  DocumentType,
} from "../src/types/graphql-api";
import { DocumentsGridView } from "../src/views/DocumentsGridView";
import { DocumentsListView } from "../src/views/DocumentsListView";
import { DocumentsCompactView } from "../src/views/DocumentsCompactView";

const row = (id: string, locked: boolean): DocumentType => ({
  id,
  title: id,
  fileType: "application/pdf",
  backendLock: locked,
  processingStatus: DocumentProcessingStatus.FAILED,
  processingError: "A required processing component is unavailable.",
  created: "2026-01-01T12:00:00Z",
  creator: { email: "owner@example.test" },
});

const documents = [
  row("Failed retained lock", true),
  row("Failed released lock", false),
];

/** Mount the real library views with terminal rows and their production styles. */
export function DocumentsFailureResponsiveTestWrapper({
  view,
}: {
  view: "grid" | "list" | "compact";
}) {
  const View = {
    grid: DocumentsGridView,
    list: DocumentsListView,
    compact: DocumentsCompactView,
  }[view];
  return (
    <View
      documents={documents}
      selectedIds={[]}
      allSelected={false}
      onDocumentClick={() => {}}
      onSelect={() => {}}
      onSelectAll={() => {}}
      onContextMenu={() => {}}
    />
  );
}

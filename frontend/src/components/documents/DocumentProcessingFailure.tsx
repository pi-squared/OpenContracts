import React from "react";
import { AlertTriangle } from "lucide-react";
import { Chip } from "@os-legal/ui";
import { DocumentType } from "../../types/graphql-api";
import { getDocumentFailureMessage } from "../../utils/documentProcessing";

/** Shared terminal state for the library's grid, list and compact views. */
export function DocumentProcessingFailure({
  document,
}: {
  document: Pick<DocumentType, "processingError">;
}) {
  return (
    <div role="status">
      <Chip size="sm" color="error" variant="soft">
        <AlertTriangle size={14} aria-hidden="true" /> Processing failed
      </Chip>
      <div>{getDocumentFailureMessage(document)}</div>
    </div>
  );
}

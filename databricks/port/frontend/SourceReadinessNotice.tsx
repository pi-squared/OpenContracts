import React from "react";
import { DocumentType } from "../../types/graphql-api";
import { getDocumentUrl } from "../../utils/navigationUtils";

export function OriginalPdfLink({
  document,
  includeTitle = false,
}: {
  document?: DocumentType | null;
  includeTitle?: boolean;
}) {
  if (
    document?.fileType !== "application/pdf" ||
    !document.slug ||
    !document.creator?.slug
  )
    return null;
  return (
    <a
      href={getDocumentUrl(document)}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(event) => event.stopPropagation()}
      style={{ display: "block" }}
    >
      Open original PDF{includeTitle ? ` — ${document.title}` : ""}
    </a>
  );
}

export function SourceReadinessNotice({
  documents,
  hasFindings,
  showOriginal = true,
  readinessError,
}: {
  documents: DocumentType[];
  hasFindings: boolean;
  showOriginal?: boolean;
  readinessError?: string | null;
}) {
  if (!readinessError && !showOriginal) return null;
  return (
    <div style={{ padding: "12px", background: "#fff4e5" }}>
      {Boolean(readinessError) && (
        <div role="alert">
          Source unavailable. {readinessError}
          {hasFindings &&
            " Existing findings are unreliable because their source is unavailable. Create a new extraction after reprocessing."}
        </div>
      )}
      {showOriginal &&
        documents.map((document) => (
          <OriginalPdfLink key={document.id} document={document} includeTitle />
        ))}
    </div>
  );
}

import React from "react";
import { DocumentType } from "../../types/graphql-api";
import { getDocumentUrl } from "../../utils/navigationUtils";

export function SourceReadinessNotice({
  documents,
  hasFindings,
  showOriginal = true,
}: {
  documents: DocumentType[];
  hasFindings: boolean;
  showOriginal?: boolean;
}) {
  const unavailable = documents.filter(
    (document) => document.extractionReadinessError
  );
  if (!unavailable.length && !showOriginal) return null;
  return (
    <div style={{ padding: "12px", background: "#fff4e5" }}>
      {unavailable.length > 0 && (
        <div role="alert">
          Source unavailable. {unavailable[0].extractionReadinessError}
          {hasFindings &&
            " Existing findings are unreliable because their source is unavailable. Create a new extraction after reprocessing."}
        </div>
      )}
      {showOriginal &&
        documents.map((document) =>
          document.fileType === "application/pdf" &&
          document.slug &&
          document.creator?.slug ? (
            <a
              key={document.id}
              href={getDocumentUrl(document)}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "block" }}
            >
              Open original PDF — {document.title}
            </a>
          ) : null
        )}
    </div>
  );
}

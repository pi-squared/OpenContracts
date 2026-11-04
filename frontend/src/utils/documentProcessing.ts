import { DocumentProcessingStatus, DocumentType } from "../types/graphql-api";

export type LibraryProcessingState = "failed" | "processing" | "processed";

/** Terminal failures override a retained lock; older records keep lock semantics. */
export function getDocumentProcessingState(
  document: Pick<DocumentType, "processingStatus" | "backendLock">
): LibraryProcessingState {
  if (document.processingStatus === DocumentProcessingStatus.FAILED) {
    return "failed";
  }
  return document.backendLock ? "processing" : "processed";
}

/** Give readers an actionable cause without backend paths or tracebacks. */
export function getDocumentFailureMessage(
  document: Pick<DocumentType, "processingError">
): string {
  if (
    /\b(model|component)\b.*\b(not found|unavailable|missing)\b|\[E050\]/i.test(
      document.processingError ?? ""
    )
  ) {
    return "A required processing component is unavailable. Contact an administrator.";
  }
  return "The document could not be processed. Contact an administrator before retrying.";
}

import { OC_EXTRACT_SOURCE_LABEL } from "../assets/configurations/constants";

/** Retained retrieval anchors support grounding and stay out of reviewer views. */
export function isReviewerVisibleLabel(
  label: { text?: string | null } | null | undefined
): boolean {
  return label?.text !== OC_EXTRACT_SOURCE_LABEL;
}

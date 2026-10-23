import { isReviewerVisibleLabel } from "../../../utils/annotationVisibility";
import { useMemo } from "react";
import { useAtomValue } from "jotai";
import { allAnnotationsAtom } from "../context/AnnotationAtoms";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "../types/annotations";

/** Returns the global, duplicate-free annotation array. */
export function useAllAnnotations(): (
  | ServerTokenAnnotation
  | ServerSpanAnnotation
)[] {
  const annotations = useAtomValue(allAnnotationsAtom);
  return useMemo(
    () =>
      annotations.filter((annotation) =>
        isReviewerVisibleLabel(annotation.annotationLabel)
      ),
    [annotations]
  );
}

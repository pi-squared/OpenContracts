// Keep the PDF interactive inside its native fullscreen dialog shell.
// Anchors allow hover revelation but own activation and text-selection admission.
export const ownsPdfEvidenceLabelInteraction = (target: EventTarget | null) =>
  target instanceof Element &&
  !!target.closest(
    "[data-annotation-label], button, [role=button]:not([data-pdf-evidence-target]), [role=dialog]:not(#knowledge-base-modal):not(#mobile-knowledge-base-modal), [data-testid=selection-action-menu]"
  );

export const ownsPdfEvidenceInteraction = (target: EventTarget | null) =>
  ownsPdfEvidenceLabelInteraction(target) ||
  (target instanceof Element && !!target.closest("a"));

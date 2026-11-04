import { atom, useAtom, useAtomValue } from "jotai";
import { useCallback, useEffect, useRef, type RefObject } from "react";
import { useLocation } from "react-router-dom";
import { useReactiveVar } from "@apollo/client";
import { selectedDocVersion } from "../graphql/cache";
import { selectedDocumentAtom } from "../components/annotator/context/DocumentAtom";
import { useAllAnnotations } from "../components/annotator/hooks/useAllAnnotations";

type EvidenceFocus = { scope: string; annotationId: string } | null;
const evidenceFocusAtom = atom<EvidenceFocus>(null);
const evidenceNavigationAtom = atom<EvidenceFocus>(null);
type InspectionIntent = { scope: string; annotationId: string | null } | null;
const inspectionIntentAtom = atom<InspectionIntent>(null);

/** Single inspection focus, independent of URL-synchronized viewer selection. */
export function useEvidenceFocus() {
  const location = useLocation();
  const document = useAtomValue(selectedDocumentAtom);
  const version = useReactiveVar(selectedDocVersion);
  const inspection = new URLSearchParams(location.search);
  const findingScope = `${inspection.get("findingCell") ?? ""}:${
    inspection.get("findingVersion") ?? "effective"
  }`;
  const scope = `${location.pathname}:${findingScope}:${version ?? "current"}:${
    document?.id ?? ""
  }:${document?.pdfFileHash ?? ""}`;
  const annotations = useAllAnnotations();
  const [focus, setFocus] = useAtom(evidenceFocusAtom);
  const [navigation, setNavigation] = useAtom(evidenceNavigationAtom);
  const [inspectionIntent, setInspectionIntent] = useAtom(inspectionIntentAtom);
  const focusedEvidenceId = focus?.scope === scope ? focus.annotationId : null;
  useEffect(() => {
    setFocus((previous) => (previous?.scope === scope ? previous : null));
    setNavigation((previous) => (previous?.scope === scope ? previous : null));
  }, [scope, setFocus, setNavigation]);
  useEffect(() => {
    if (
      focusedEvidenceId &&
      !annotations.some((item) => item.id === focusedEvidenceId)
    ) {
      setFocus(null);
      setNavigation(null);
    }
  }, [focusedEvidenceId, annotations, setFocus, setNavigation]);
  const setFocusedEvidence = useCallback(
    (annotationId: string | null) => {
      // Record explicit actions even when loading has already cleared focus.
      // Automatic source/scope invalidation above does not alter this intent.
      setInspectionIntent({ scope, annotationId });
      setFocus(annotationId ? { scope, annotationId } : null);
    },
    [scope, setFocus, setInspectionIntent]
  );
  const navigateToEvidence = useCallback(
    (annotationId: string, origin: "inspection" | "entry" = "inspection") => {
      if (origin === "entry") setFocus({ scope, annotationId });
      else setFocusedEvidence(annotationId);
      setNavigation({ scope, annotationId });
    },
    [scope, setFocus, setFocusedEvidence, setNavigation]
  );
  return {
    focusedEvidenceId,
    // Retain the request identity so repeated activation of one highlight can
    // reveal its card again after the user scrolls away or collapses its group.
    focusRequest: focusedEvidenceId ? focus : null,
    setFocusedEvidence,
    navigateToEvidence,
    evidenceNavigation: navigation?.scope === scope ? navigation : null,
    evidenceScope: scope,
    inspectionIntent:
      inspectionIntent?.scope === scope ? inspectionIntent : null,
  };
}

/** Native document owners handle Escape before the PDF inspection fallback. */
export function useEvidenceFocusEscape(viewer: RefObject<HTMLElement> | null) {
  const { setFocusedEvidence } = useEvidenceFocus();
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const target = event.target;
      if (
        !(target instanceof Element) ||
        (target !== document.body && !viewer?.current?.contains(target))
      )
        return;
      if (
        target.closest('input, textarea, select, [contenteditable="true"]') ||
        document.querySelector(
          '[role="dialog"]:not(#knowledge-base-modal):not(#mobile-knowledge-base-modal)'
        )
      )
        return;
      const selection = window.getSelection();
      if (selection && !selection.isCollapsed) {
        event.preventDefault();
        selection.removeAllRanges();
        return;
      }
      setFocusedEvidence(null);
    };
    // Window bubbling follows native dialog/filter/selection document handlers.
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [viewer, setFocusedEvidence]);
}

/** Explicit evidence entry targets seed focus once after the native loader locates them. */
export function useEvidenceFocusNavigation() {
  const location = useLocation();
  const annotations = useAllAnnotations();
  const { evidenceScope, inspectionIntent, navigateToEvidence } =
    useEvidenceFocus();
  const entry = new URLSearchParams(location.search).get("ann") ?? "";
  const handled = useRef<{
    key: string;
    intent: InspectionIntent;
    pending: boolean;
    dismissed: boolean;
  } | null>(null);
  useEffect(() => {
    const key = `${evidenceScope}:${entry}`;
    if (!entry) {
      handled.current = null;
      return;
    }
    if (handled.current?.key !== key)
      handled.current = {
        key,
        intent: inspectionIntent,
        pending: true,
        dismissed: false,
      };
    const request = handled.current;
    // Pending entries retain manual authority while their projection is absent,
    // including Escape with no focus and inspection batched with replacement.
    if (request.intent !== inspectionIntent) request.dismissed = true;
    if (request.dismissed) return;
    const ids = entry.split(",");
    const target = ids
      .map((id) =>
        annotations.find(
          (annotation) => annotation.id === id && annotation.isEvidenceQuote
        )
      )
      .find(Boolean);
    if (!target) {
      // Extract loading replaces the initial document annotations. An entry
      // consumed before that replacement still needs its final source.
      request.pending = true;
      return;
    }
    if (!request.pending) return;
    request.pending = false;
    navigateToEvidence(target.id, "entry");
  }, [entry, evidenceScope, annotations, inspectionIntent, navigateToEvidence]);
}

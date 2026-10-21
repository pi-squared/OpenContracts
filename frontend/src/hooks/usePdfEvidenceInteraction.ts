import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";
import { ServerTokenAnnotation } from "../components/annotator/types/annotations";
import { PDFPageInfo } from "../components/annotator/types/pdf";
import { useEvidenceFocus } from "./useEvidenceFocus";

import {
  ANNOTATION_LABEL_HOVER_EXIT_DELAY_MS,
  PDF_EVIDENCE_MOVEMENT_THRESHOLD_PX,
  PDF_EVIDENCE_TOUCH_HOLD_DURATION_MS,
} from "../assets/configurations/constants";
import {
  ownsPdfEvidenceInteraction,
  ownsPdfEvidenceLabelInteraction,
} from "../utils/pdfEvidenceInteraction";

/** Inspect eligible evidence at a page point without changing viewer selection. */
export function usePdfEvidenceInteraction(
  canvas: RefObject<HTMLCanvasElement>,
  pageInfo: PDFPageInfo,
  annotations: ServerTokenAnnotation[]
) {
  const { focusedEvidenceId, setFocusedEvidence } = useEvidenceFocus();
  const [hoveredEvidenceIds, setHoveredEvidenceIds] = useState<string[]>([]);
  const hoverExitTimer = useRef<ReturnType<typeof setTimeout>>();
  const mouseStart = useRef<{ x: number; y: number; moved: boolean } | null>(
    null
  );
  const touchPress = useRef<{
    id: number;
    x: number;
    y: number;
    moved: boolean;
    started: number;
  } | null>(null);
  const rejectTouchClick = useRef(false);

  useEffect(() => {
    // Remember movement outside this page too: returning to the press point
    // still ends a drag, rather than admitting a stationary evidence click.
    const move = (event: globalThis.MouseEvent) => {
      const start = mouseStart.current;
      if (
        start &&
        event.buttons & 1 &&
        Math.hypot(event.clientX - start.x, event.clientY - start.y) >
        PDF_EVIDENCE_MOVEMENT_THRESHOLD_PX
      )
        start.moved = true;
    };
    const cancel = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      mouseStart.current = null;
      if (touchPress.current) {
        touchPress.current = null;
        rejectTouchClick.current = true;
      }
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("keydown", cancel);
    return () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("keydown", cancel);
    };
  }, []);

  const candidatesAt = useCallback(
    (clientX: number, clientY: number) => {
      const rect = canvas.current?.getBoundingClientRect();
      if (!rect) return [];
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      const candidates = new Set<string>();
      for (const annotation of annotations) {
        if (!annotation.isEvidenceQuote) continue;
        const page = annotation.json[pageInfo.page.pageNumber - 1];
        if (!page?.bounds) continue;
        const bounds = pageInfo.getScaledBounds(page.bounds);
        if (
          x >= Math.min(bounds.left, bounds.right) &&
          x <= Math.max(bounds.left, bounds.right) &&
          y >= Math.min(bounds.top, bounds.bottom) &&
          y <= Math.max(bounds.top, bounds.bottom)
        )
          candidates.add(annotation.id);
      }
      // Identity order remains stable across hover stacking and finding reuse.
      return [...candidates].sort();
    },
    [annotations, canvas, pageInfo]
  );

  const activateAt = useCallback(
    (clientX: number, clientY: number) => {
      const candidates = candidatesAt(clientX, clientY);
      const index = focusedEvidenceId
        ? candidates.indexOf(focusedEvidenceId)
        : -1;
      setFocusedEvidence(candidates[(index + 1) % candidates.length] ?? null);
    },
    [candidatesAt, focusedEvidenceId, setFocusedEvidence]
  );

  const leave = useCallback(() => {
    clearTimeout(hoverExitTimer.current);
    hoverExitTimer.current = setTimeout(
      () => setHoveredEvidenceIds([]),
      ANNOTATION_LABEL_HOVER_EXIT_DELAY_MS
    );
  }, []);
  useEffect(() => () => clearTimeout(hoverExitTimer.current), []);

  const onMouseMoveCapture = (event: MouseEvent) => {
    const start = mouseStart.current;
    if (
      start &&
      Math.hypot(event.clientX - start.x, event.clientY - start.y) >
        PDF_EVIDENCE_MOVEMENT_THRESHOLD_PX
    )
      start.moved = true;
    clearTimeout(hoverExitTimer.current);
    if (ownsPdfEvidenceLabelInteraction(event.target)) return;
    const candidates = candidatesAt(event.clientX, event.clientY);
    if (candidates.length) setHoveredEvidenceIds(candidates);
    else leave();
  };

  useEffect(() => {
    if (!hoveredEvidenceIds.length) return;
    const pointerLeave = (event: PointerEvent) => {
      const wrapper = canvas.current?.parentElement;
      if (event.target instanceof Node && !wrapper?.contains(event.target))
        leave();
    };
    document.addEventListener("pointermove", pointerLeave);
    return () => document.removeEventListener("pointermove", pointerLeave);
  }, [canvas, hoveredEvidenceIds, leave]);

  return {
    hoveredEvidenceIds,
    activateAt,
    mouseHandlers: {
      onPointerDownCapture: (event: ReactPointerEvent) => {
        if (event.pointerType === "mouse") rejectTouchClick.current = false;
        if (event.pointerType !== "touch") return;
        if (touchPress.current || !event.isPrimary) {
          if (touchPress.current) touchPress.current.moved = true;
          rejectTouchClick.current = true;
          return;
        }
        if (ownsPdfEvidenceInteraction(event.target)) return;
        rejectTouchClick.current = false;
        touchPress.current = {
          id: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          moved: false,
          started: performance.now(),
        };
      },
      onPointerMoveCapture: (event: ReactPointerEvent) => {
        const start = touchPress.current;
        if (
          start?.id === event.pointerId &&
          Math.hypot(event.clientX - start.x, event.clientY - start.y) >
            PDF_EVIDENCE_MOVEMENT_THRESHOLD_PX
        )
          start.moved = true;
      },
      onPointerUpCapture: (event: ReactPointerEvent) => {
        const start = touchPress.current;
        if (start?.id !== event.pointerId) return;
        rejectTouchClick.current =
          start.moved ||
          Math.hypot(event.clientX - start.x, event.clientY - start.y) >
            PDF_EVIDENCE_MOVEMENT_THRESHOLD_PX ||
          performance.now() - start.started >=
            PDF_EVIDENCE_TOUCH_HOLD_DURATION_MS;
        touchPress.current = null;
      },
      onPointerCancelCapture: (event: ReactPointerEvent) => {
        if (touchPress.current?.id !== event.pointerId) return;
        touchPress.current = null;
        rejectTouchClick.current = true;
      },
      onMouseDownCapture: (event: MouseEvent) => {
        mouseStart.current =
          event.button === 0 &&
          !rejectTouchClick.current &&
          !event.shiftKey &&
          !event.ctrlKey &&
          !event.metaKey &&
          !event.altKey &&
          !ownsPdfEvidenceInteraction(event.target)
            ? { x: event.clientX, y: event.clientY, moved: false }
            : null;
      },
      onMouseMoveCapture,
      onMouseLeave: leave,
      onClick: (event: MouseEvent) => {
        const start = mouseStart.current;
        mouseStart.current = null;
        if (
          !start ||
          start.moved ||
          event.defaultPrevented ||
          ownsPdfEvidenceInteraction(event.target)
        )
          return;
        if (
          Math.hypot(event.clientX - start.x, event.clientY - start.y) >
          PDF_EVIDENCE_MOVEMENT_THRESHOLD_PX
        )
          return;
        activateAt(event.clientX, event.clientY);
      },
    },
  };
}

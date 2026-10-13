import { RefObject, useLayoutEffect } from "react";
import {
  ANNOTATION_LABEL_GAP,
  ANNOTATION_LABEL_MIN_HEIGHT,
} from "../assets/configurations/constants";

/** Place visible label bars using their rendered size; boxes retain PDF coordinates. */
export function useAnnotationLabelLayout(
  container: RefObject<HTMLElement>,
  revision: unknown,
  zoom: number
) {
  useLayoutEffect(() => {
    const page = container.current;
    if (!page) return;
    let frame = 0;
    const layout = () => {
      const labels = Array.from(
        page.querySelectorAll<HTMLElement>("[data-annotation-label]")
      );
      labels.forEach((label) => {
        label.style.transform = "";
      });
      const pageBounds = page.getBoundingClientRect();
      const items = labels
        .map((label) => ({ label, bounds: label.getBoundingClientRect() }))
        .filter(
          ({ label, bounds }) =>
            bounds.height > ANNOTATION_LABEL_MIN_HEIGHT &&
            !!label.innerText.trim()
        )
        .sort(
          (a, b) =>
            a.bounds.top - b.bounds.top ||
            a.bounds.left - b.bounds.left ||
            a.label.dataset.annotationLabel!.localeCompare(
              b.label.dataset.annotationLabel!
            )
        );
      const placed: {
        left: number;
        right: number;
        top: number;
        bottom: number;
      }[] = [];
      for (const { label, bounds } of items) {
        const dx = Math.max(
          pageBounds.left - bounds.left,
          Math.min(0, pageBounds.right - bounds.right)
        );
        let top = bounds.top;
        // Move above each conflicting bar, including slightly different source boxes.
        for (let attempts = 0; attempts <= placed.length; attempts++) {
          const conflicts = placed.filter(
            (other) =>
              bounds.left + dx < other.right + ANNOTATION_LABEL_GAP &&
              bounds.right + dx > other.left - ANNOTATION_LABEL_GAP &&
              top < other.bottom + ANNOTATION_LABEL_GAP &&
              top + bounds.height > other.top - ANNOTATION_LABEL_GAP
          );
          if (!conflicts.length) break;
          top =
            Math.min(...conflicts.map((other) => other.top)) -
            bounds.height -
            ANNOTATION_LABEL_GAP;
        }
        const dy = top - bounds.top;
        label.style.transform = `translate(${dx}px, ${dy}px)`;
        label.style.setProperty("--label-lift", `${-dy}px`);
        label.style.setProperty("--label-shift", `${dx}px`);
        placed.push({
          left: bounds.left + dx,
          right: bounds.right + dx,
          top,
          bottom: top + bounds.height,
        });
      }
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(layout);
    };
    const resize =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(schedule);
    resize?.observe(page);
    window.addEventListener("resize", schedule);
    const changes = new MutationObserver(schedule);
    changes.observe(page, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "hidden"],
    });
    layout();
    return () => {
      cancelAnimationFrame(frame);
      resize?.disconnect();
      changes.disconnect();
      window.removeEventListener("resize", schedule);
    };
  }, [container, revision, zoom]);
}

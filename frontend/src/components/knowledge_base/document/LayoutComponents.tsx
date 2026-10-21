import React, { useEffect, useRef } from "react";
import { Modal } from "@os-legal/ui";
import styled, { createGlobalStyle } from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

export const DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS =
  "document-kb-child-modal-overlay";

const childDialogStack: HTMLElement[] = [];
const focusableSelector =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Native viewer child dialog: portal layer, scoped focus and launcher return. */
export const DocumentChildModal = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<typeof Modal>
>(
  (
    {
      open,
      onClose,
      children,
      overlayClassName,
      closeOnEscape = true,
      ...props
    },
    forwardedRef
  ) => {
    const dialogRef = useRef<HTMLDivElement | null>(null);
    const closeRef = useRef(onClose);
    closeRef.current = onClose;
    useEffect(() => {
      const dialog = dialogRef.current;
      if (!open || !dialog) return;
      const launcher =
        document.activeElement instanceof HTMLElement ||
        document.activeElement instanceof SVGElement
          ? document.activeElement
          : null;
      childDialogStack.push(dialog);
      const isTopmost = () =>
        childDialogStack[childDialogStack.length - 1] === dialog;
      const ownedPortals = () =>
        Array.from(dialog.querySelectorAll("[aria-controls]"))
          .map((control) =>
            document.getElementById(control.getAttribute("aria-controls") ?? "")
          )
          .filter((element): element is HTMLElement => element !== null);
      const containsFocus = (target: Node | null) =>
        !!target &&
        (dialog.contains(target) ||
          ownedPortals().some((portal) => portal.contains(target)));
      const focusable = () =>
        [dialog, ...ownedPortals()]
          .flatMap((region) =>
            Array.from(region.querySelectorAll<HTMLElement>(focusableSelector))
          )
          .filter(
            (element) =>
              element.getClientRects().length > 0 && !element.closest("[inert]")
          );
      const focusFirst = () => (focusable()[0] ?? dialog).focus();
      focusFirst();
      const handleFocus = (event: FocusEvent) => {
        if (isTopmost() && !containsFocus(event.target as Node)) focusFirst();
      };
      const handleKey = (event: KeyboardEvent) => {
        if (!isTopmost()) return;
        if (event.key === "Escape" && closeOnEscape) {
          // Let an open native picker dismiss its popup before the dialog.
          if (dialog.querySelector('[aria-expanded="true"]')) return;
          event.preventDefault();
          event.stopPropagation();
          closeRef.current();
        } else if (event.key === "Tab") {
          const items = focusable();
          const index = items.indexOf(document.activeElement as HTMLElement);
          const next = event.shiftKey
            ? index <= 0
              ? items.length - 1
              : index - 1
            : (index + 1) % items.length;
          event.preventDefault();
          event.stopPropagation();
          (items[next] ?? dialog).focus();
        }
      };
      document.addEventListener("keydown", handleKey, true);
      document.addEventListener("focusin", handleFocus);
      return () => {
        const index = childDialogStack.indexOf(dialog);
        if (index >= 0) childDialogStack.splice(index, 1);
        document.removeEventListener("keydown", handleKey, true);
        document.removeEventListener("focusin", handleFocus);
        if (launcher?.isConnected) launcher.focus();
      };
    }, [open, closeOnEscape]);
    return (
      <Modal
        {...props}
        open={open}
        onClose={onClose}
        closeOnEscape={false}
        overlayClassName={[
          DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS,
          overlayClassName,
        ]
          .filter(Boolean)
          .join(" ")}
        tabIndex={-1}
        ref={(node) => {
          dialogRef.current = node;
          if (typeof forwardedRef === "function") forwardedRef(node);
          else if (forwardedRef) forwardedRef.current = node;
        }}
      >
        {children}
      </Modal>
    );
  }
);
DocumentChildModal.displayName = "DocumentChildModal";

// Minimal overrides for the fullscreen modal body — the native size="fullscreen"
// variant handles positioning, sizing, border-radius, and overlay padding.
// We override max-height because the base .oc-modal sets max-height: calc(100vh - 32px)
// which the fullscreen variant doesn't clear, and overflow: hidden to contain content.
// Injected unconditionally when FullScreenModal is mounted (even when closed),
// but scoped via DKB modal classes to prevent leakage.
//
// The pervasive ``!important`` annotations below are fighting the higher
// specificity of @os-legal/ui's internal modal styles. If you remove or
// reorder them be prepared to also fix overlay positioning, modal sizing,
// and scroll-lock behaviour on mobile — they are load-bearing, not stylistic.
const FullScreenModalBodyStyles = createGlobalStyle`
  html.document-kb-scroll-lock,
  body.document-kb-scroll-lock {
    height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    min-height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    max-height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    overflow: hidden !important;
    overscroll-behavior: none;
  }

  body.document-kb-scroll-lock {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
  }

  html.document-kb-scroll-lock #root {
    height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    min-height: 0 !important;
    max-height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    overflow: hidden !important;
  }

  .fullscreen-modal-overlay {
    position: fixed !important;
    inset: 0 !important;
    align-items: stretch;
    justify-content: stretch;
    padding: 0 !important;
    z-index: var(--oc-app-modal-z-index, 3000);
    height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    max-height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    overflow: hidden !important;
    overscroll-behavior: none;
  }

  .fullscreen-modal {
    position: fixed !important;
    inset: 0 !important;
    background: ${OS_LEGAL_COLORS.gray50};
    width: 100vw !important;
    max-width: 100vw !important;
    height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    max-height: var(--oc-dkb-visible-viewport-height, var(--oc-visible-viewport-height, 100vh)) !important;
    margin: 0 !important;
    border-radius: 0 !important;
    overflow: hidden;
    min-height: 0;
  }

  .fullscreen-modal,
  .fullscreen-modal *,
  .fullscreen-modal *::before,
  .fullscreen-modal *::after {
    box-sizing: border-box;
  }

  .fullscreen-modal .oc-modal-body {
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
  }

  .oc-modal-overlay.${DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS} {
    z-index: var(--oc-app-modal-child-z-index, 3100);
  }
`;

interface FullScreenModalProps {
  id?: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

/**
 * Module-level counter of how many ``FullScreenModal`` instances are
 * currently open. The scroll-lock classes are added on the first mount
 * and only stripped on the last unmount, so nested modals (a child
 * dialog opened on top of the DocumentKnowledgeBase fullscreen modal,
 * for example) don't accidentally release the body scroll lock while
 * a parent is still open.
 */
let fullScreenModalOpenCount = 0;

export const FullScreenModal: React.FC<FullScreenModalProps> = ({
  id,
  open,
  onClose,
  children,
}) => {
  useEffect(() => {
    if (!open) return;

    const root = document.documentElement;
    const scrollY = window.scrollY;
    const updateViewportVars = () => {
      const visualViewport = window.visualViewport;
      root.style.setProperty(
        "--oc-dkb-visible-viewport-height",
        `${visualViewport?.height ?? window.innerHeight}px`
      );
      root.style.setProperty(
        "--oc-dkb-visible-viewport-offset-top",
        `${visualViewport?.offsetTop ?? 0}px`
      );
    };

    updateViewportVars();
    window.addEventListener("resize", updateViewportVars);
    window.visualViewport?.addEventListener("resize", updateViewportVars);
    window.visualViewport?.addEventListener("scroll", updateViewportVars);

    // Increment the global counter and only add the lock classes (and reset
    // page scroll to the top) on the first open. Nested FullScreenModal
    // instances share the lock — they should not re-trigger scrollTo.
    fullScreenModalOpenCount += 1;
    if (fullScreenModalOpenCount === 1) {
      window.scrollTo(0, 0);
      root.classList.add("document-kb-scroll-lock");
      document.body.classList.add("document-kb-scroll-lock");
    }

    return () => {
      window.removeEventListener("resize", updateViewportVars);
      window.visualViewport?.removeEventListener("resize", updateViewportVars);
      window.visualViewport?.removeEventListener("scroll", updateViewportVars);
      // Only strip the lock when the last open instance unmounts so that
      // a child modal closing first doesn't release the parent's lock.
      fullScreenModalOpenCount = Math.max(0, fullScreenModalOpenCount - 1);
      if (fullScreenModalOpenCount === 0) {
        root.style.removeProperty("--oc-dkb-visible-viewport-height");
        root.style.removeProperty("--oc-dkb-visible-viewport-offset-top");
        root.classList.remove("document-kb-scroll-lock");
        document.body.classList.remove("document-kb-scroll-lock");
        window.scrollTo(0, scrollY);
      }
    };
  }, [open]);

  return (
    <>
      <FullScreenModalBodyStyles />
      <Modal
        id={id}
        open={open}
        onClose={onClose}
        size="fullscreen"
        className="fullscreen-modal"
        overlayClassName="fullscreen-modal-overlay"
        closeOnEscape={false}
        closeOnOverlay={false}
      >
        {children}
      </Modal>
    </>
  );
};

/* Indigo palette — no OS_LEGAL_COLORS tokens yet; add when indigo tokens are introduced */
export const SourceIndicator = styled.div`
  padding: 0.5rem;
  background: #eef2ff;
  border-left: 3px solid #818cf8;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  color: #4338ca;
`;

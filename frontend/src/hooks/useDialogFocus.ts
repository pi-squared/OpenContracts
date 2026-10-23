import { RefObject, useEffect, useRef } from "react";

// Child dialogs may render through a body portal rather than inside their parent.
const dialogs: HTMLElement[] = [];

/** Keyboard containment and launcher restoration for custom dialogs. */
export function useDialogFocus(
  open: boolean,
  dialog: RefObject<HTMLElement>,
  onClose: () => void
) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const element = dialog.current;
    if (!open || !element) return;
    const launcher = document.activeElement as HTMLElement | null;
    dialogs.push(element);
    const active = () => dialogs[dialogs.length - 1] === element;
    const controls = () =>
      Array.from(
        element.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]'
        )
      ).filter((control) => control.getClientRects().length > 0);
    const focusFirst = () => (controls()[0] ?? element).focus();
    focusFirst();
    const keydown = (event: KeyboardEvent) => {
      if (!active()) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close.current();
      } else if (event.key === "Tab") {
        const targets = controls();
        const current = targets.indexOf(document.activeElement as HTMLElement);
        if (!targets.length) {
          event.preventDefault();
          element.focus();
        } else if (event.shiftKey && current <= 0) {
          event.preventDefault();
          targets[targets.length - 1].focus();
        } else if (
          !event.shiftKey &&
          (current < 0 || current === targets.length - 1)
        ) {
          event.preventDefault();
          targets[0].focus();
        }
      }
    };
    const focusin = (event: FocusEvent) => {
      if (!active()) return;
      if (!element.contains(event.target as Node)) focusFirst();
    };
    document.addEventListener("keydown", keydown, true);
    document.addEventListener("focusin", focusin);
    return () => {
      document.removeEventListener("keydown", keydown, true);
      document.removeEventListener("focusin", focusin);
      dialogs.splice(dialogs.indexOf(element), 1);
      if (launcher?.isConnected) launcher.focus();
      const parent = dialogs[dialogs.length - 1];
      if (parent && !parent.contains(document.activeElement)) parent.focus();
    };
  }, [open, dialog]);
}

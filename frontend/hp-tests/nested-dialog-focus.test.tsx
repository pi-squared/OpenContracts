import React, { act, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { createPortal } from "react-dom";
import { expect, it, vi } from "vitest";
import { useDialogFocus } from "../src/hooks/useDialogFocus";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

function Child({ close }: { close: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useDialogFocus(true, ref, close);
  return createPortal(
    <div ref={ref} role="dialog" aria-label="Child" tabIndex={-1}>
      <input aria-label="Child name" />
      <button onClick={close}>Cancel child</button>
    </div>,
    document.body
  );
}

function Parent({ close }: { close: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [child, setChild] = useState(false);
  useDialogFocus(true, ref, close);
  return (
    <div ref={ref} role="dialog" aria-label="Parent" tabIndex={-1}>
      {!child && <button onClick={() => setChild(true)}>Open child</button>}
      <button onClick={close}>Cancel parent</button>
      {child && <Child close={() => setChild(false)} />}
    </div>
  );
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open parent</button>
      {open && <Parent close={() => setOpen(false)} />}
    </>
  );
}

it("returns focus to the parent when a portalled child's launcher unmounts", () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const visible = vi
    .spyOn(HTMLElement.prototype, "getClientRects")
    .mockImplementation(() =>
      Object.assign([new DOMRect()], { item: () => null })
    );
  try {
    act(() => root.render(<Harness />));
    const launcher = host.querySelector("button")!;
    launcher.focus();
    act(() => launcher.click());
    const childLauncher = host.querySelector('[aria-label="Parent"] button')!;
    act(() =>
      childLauncher.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    );
    const child = document.querySelector('[aria-label="Child"]')!;
    expect(child.contains(document.activeElement)).toBe(true);
    expect(childLauncher.isConnected).toBe(false);
    act(() =>
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
      )
    );
    expect(document.querySelector('[aria-label="Child"]')).toBeNull();
    expect(
      host
        .querySelector('[aria-label="Parent"]')
        ?.contains(document.activeElement)
    ).toBe(true);
    act(() =>
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
      )
    );
    expect(document.activeElement).toBe(launcher);
  } finally {
    act(() => root.unmount());
    host.remove();
    visible.mockRestore();
  }
});

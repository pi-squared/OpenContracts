import React, { act, useState } from "react";
import { createRoot, Root } from "react-dom/client";
import { Simulate } from "react-dom/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CellEditor } from "../src/components/annotator/sidebar/CellEditor";
import {
  rejectReviewQuotation,
  reviewQuotations,
  ReviewSaveOptions,
} from "../src/utils/reviewerFeedback";

vi.mock("react-json-view", () => ({ default: () => <div>Raw editor</div> }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
const first = { quote: "Total price: ____", page: 2 };
const second = { quote: "Schedule of payments", page: 3 };
const finding = {
  finding: "present_blank",
  rationale: "The price field is blank.",
  evidence: [first, second],
};
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});
function button(text: string) {
  const e = Array.from(host.querySelectorAll("button")).find(
    (e) => e.textContent === text
  );
  expect(e).toBeDefined();
  return e!;
}
function rejectFirst() {
  act(() =>
    host
      .querySelector<HTMLButtonElement>('[aria-label="Reject quotation 1"]')!
      .click()
  );
}

it("requires confirmation and keeps the quotation when the user cancels", () => {
  const save = vi.fn();
  const close = vi.fn();
  act(() =>
    root.render(
      <CellEditor
        value={finding}
        onSave={save}
        onClose={close}
        loading={false}
      />
    )
  );
  act(() => button("Evidence").click());
  rejectFirst();
  expect(host.querySelector('[role="alertdialog"]')?.textContent).toContain(
    first.quote
  );
  expect(save).not.toHaveBeenCalled();
  expect(host.querySelectorAll("article")).toHaveLength(2);
  act(() => button("Keep quotation").click());
  expect(host.querySelector('[role="alertdialog"]')).toBeNull();
  expect(host.querySelectorAll("article")).toHaveLength(2);
  rejectFirst();
  act(() =>
    Simulate.keyDown(host.querySelector('[role="alertdialog"]')!, {
      key: "Escape",
    })
  );
  expect(close).not.toHaveBeenCalled();
  expect(save).not.toHaveBeenCalled();
});

it("saves a confirmed correction, removes that quote and retains unsaved comment drafts", async () => {
  const save = vi.fn();
  const before = JSON.stringify(finding);
  function Harness() {
    const [value, setValue] = useState<unknown>(finding);
    return (
      <CellEditor
        value={value}
        loading={false}
        onClose={() => {}}
        onSave={async (next, options?: ReviewSaveOptions) => {
          save(next, options);
          setValue(next);
          return true;
        }}
      />
    );
  }
  act(() => root.render(<Harness />));
  act(() =>
    Simulate.change(host.querySelector("textarea")!, {
      target: { value: "Unsaved verdict draft" },
    })
  );
  act(() => button("Evidence").click());
  rejectFirst();
  await act(async () => {
    button("Confirm rejection").click();
    await Promise.resolve();
  });
  expect(save).toHaveBeenCalledOnce();
  expect(save.mock.calls[0][1]).toEqual({
    keepOpen: true,
    successMessage: "Quotation rejected.",
  });
  const saved = save.mock.calls[0][0];
  expect(saved.data.evidence).toEqual([second]);
  expect(saved.reviewer_feedback.rejected_quotations[0].quotation).toEqual(
    first
  );
  expect(saved.reviewer_feedback.verdict_comment).toBeUndefined();
  expect(host.querySelectorAll("article")).toHaveLength(1);
  expect(host.querySelector("article")?.textContent).toContain(second.quote);
  expect(host.querySelector('[role="alertdialog"]')).toBeNull();
  act(() => button("Verdict").click());
  expect(host.querySelector("textarea")?.value).toBe("Unsaved verdict draft");
  expect(JSON.stringify(finding)).toBe(before);
});

it("retains the quotation and confirmation on save failure", async () => {
  const save = vi.fn().mockResolvedValue(false);
  act(() =>
    root.render(
      <CellEditor
        value={finding}
        onSave={save}
        onClose={() => {}}
        loading={false}
      />
    )
  );
  act(() => button("Evidence").click());
  rejectFirst();
  await act(async () => {
    button("Confirm rejection").click();
    await Promise.resolve();
  });
  expect(host.querySelectorAll("article")).toHaveLength(2);
  expect(host.querySelector('[role="alert"]')?.textContent).toContain(
    "could not be rejected"
  );
  expect(host.querySelector('[role="alertdialog"]')).not.toBeNull();
});

it("preserves encoded evidence and unrelated metadata, and refuses a stale target", () => {
  const value = {
    data: {
      ...finding,
      evidence: JSON.stringify([first, second]),
      reviewer_feedback: { verdict_comment: "Keep this comment" },
    },
    version: 2,
  };
  const target = reviewQuotations(value)[0];
  const updated = rejectReviewQuotation(value, target);
  expect(updated).toMatchObject({
    version: 2,
    data: { evidence: JSON.stringify([second]) },
    reviewer_feedback: { verdict_comment: "Keep this comment" },
  });
  expect(rejectReviewQuotation(updated, target)).toBe(updated);
  expect(reviewQuotations({ ...finding, finding: "not_found" })).toEqual([]);
});

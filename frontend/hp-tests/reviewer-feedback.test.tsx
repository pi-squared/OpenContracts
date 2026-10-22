import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { Simulate } from "react-dom/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CellEditor } from "../src/components/annotator/sidebar/CellEditor";
import {
  readReviewerFeedback,
  withReviewerFeedback,
} from "../src/utils/reviewerFeedback";

vi.mock("react-json-view", () => ({
  default: () => <div>Raw data editor</div>,
}));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
const finding = {
  finding: "present_blank",
  rationale: "The price field is blank.",
  evidence: [{ quote: "Total price: ____", page: null }],
  customer_purpose: "consumer",
};

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function button(text: string) {
  const found = Array.from(host.querySelectorAll("button")).find(
    (e) => e.textContent === text
  );
  expect(found).toBeDefined();
  return found!;
}
function comment(text: string) {
  const textarea = host.querySelector("textarea")!;
  act(() => Simulate.change(textarea, { target: { value: text } }));
}

it("saves separate comments and preserves the verdict, rationale and all evidence", () => {
  const save = vi.fn();
  const before = JSON.stringify(finding);
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
  expect(host.textContent).not.toContain("Raw data editor");
  expect(button("Save comments").disabled).toBe(true);
  comment("The blank-field verdict is appropriate.");
  act(() => button("Evidence").click());
  expect(host.textContent).toContain("Total price: ____");
  comment("Please also include the schedule heading.");
  act(() => button("Verdict").click());
  expect(host.querySelector("textarea")?.value).toBe(
    "The blank-field verdict is appropriate."
  );
  act(() => button("Save comments").click());
  expect(save).toHaveBeenCalledExactlyOnceWith({
    data: finding,
    reviewer_feedback: {
      verdict_comment: "The blank-field verdict is appropriate.",
      evidence_comment: "Please also include the schedule heading.",
    },
  });
  expect(JSON.stringify(finding)).toBe(before);
});

it("reopens saved comments and keeps drafts during a failed-save loading cycle", () => {
  const value = withReviewerFeedback(finding, {
    verdict: "Saved verdict comment",
    evidence: "Saved evidence comment",
  });
  const save = vi.fn();
  const render = (loading: boolean) =>
    act(() =>
      root.render(
        <CellEditor
          value={value}
          onSave={save}
          onClose={() => {}}
          loading={loading}
        />
      )
    );
  render(false);
  expect(host.querySelector("textarea")?.value).toBe("Saved verdict comment");
  expect(button("Save comments").disabled).toBe(true);
  comment("Revised verdict comment");
  render(true);
  expect(host.querySelector("textarea")?.disabled).toBe(true);
  expect(button("Saving…").disabled).toBe(true);
  render(false);
  expect(host.querySelector("textarea")?.value).toBe("Revised verdict comment");
  act(() => button("Evidence").click());
  expect(host.querySelector("textarea")?.value).toBe("Saved evidence comment");
  expect(button("Save comments").disabled).toBe(false);
});

it("retains hidden not-found evidence and existing feedback metadata inside an envelope", () => {
  const value = {
    data: {
      ...finding,
      finding: "not_found",
      reviewer_feedback: { audit: "keep", verdict_comment: "old" },
    },
    version: 2,
  };
  const updated = withReviewerFeedback(value, {
    verdict: "new",
    evidence: "Retain the source.",
  });
  expect(updated).toEqual({
    version: 2,
    data: { ...finding, finding: "not_found" },
    reviewer_feedback: {
      audit: "keep",
      verdict_comment: "new",
      evidence_comment: "Retain the source.",
    },
  });
  expect(readReviewerFeedback(updated)).toEqual({
    verdict: "new",
    evidence: "Retain the source.",
  });
  expect(value.data.reviewer_feedback.verdict_comment).toBe("old");
});

it("supports keyboard topic changes and Escape without saving", () => {
  const close = vi.fn();
  const save = vi.fn();
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
  act(() => Simulate.keyDown(button("Verdict"), { key: "ArrowRight" }));
  expect(button("Evidence").getAttribute("aria-selected")).toBe("true");
  act(() => Simulate.keyDown(host.querySelector("form")!, { key: "Escape" }));
  expect(close).toHaveBeenCalledOnce();
  expect(save).not.toHaveBeenCalled();
});

it("keeps the raw editor for unrelated structured values", () => {
  act(() =>
    root.render(
      <CellEditor
        value={{ amount: 500 }}
        onSave={() => {}}
        onClose={() => {}}
        loading={false}
      />
    )
  );
  expect(host.textContent).toContain("Raw data editor");
  expect(host.textContent).not.toContain("Review extraction");
});

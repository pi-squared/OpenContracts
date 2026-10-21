import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { CellEditor } from "../src/components/annotator/sidebar/CellEditor";

const editor = vi.hoisted(() => ({ props: null as any }));
vi.mock("react-json-view", () => ({
  default: (props: any) => {
    editor.props = props;
    return <div>{JSON.stringify(props.src)}</div>;
  },
}));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const host = document.createElement("div");
const root = createRoot(host);
afterEach(() => act(() => root.render(null)));

it("round trips hidden evidence through the editor's real deletion callback and outcome changes", () => {
  const save = vi.fn();
  const first = { scope: "first", evidence_quote: "first hidden quote" };
  const second = { scope: "second", evidence_quote: "second hidden quote" };
  act(() =>
    root.render(
      <CellEditor
        value={{
          finding: "not_found",
          rationale: "Initial",
          scoped_entries: [first, second],
        }}
        onSave={save}
        onClose={() => {}}
        loading={false}
      />
    )
  );
  expect(host.textContent).not.toContain("hidden quote");
  // react-json-view supplies namespace/name, without a type discriminator.
  act(() =>
    editor.props.onDelete({
      namespace: ["scoped_entries"],
      name: "0",
      updated_src: {
        ...editor.props.src,
        scoped_entries: [{ scope: "second" }],
      },
    })
  );
  act(() =>
    editor.props.onEdit({
      updated_src: { ...editor.props.src, rationale: "Edited" },
    })
  );
  act(() =>
    editor.props.onEdit({
      updated_src: { ...editor.props.src, finding: "uncertain" },
    })
  );
  expect(host.textContent).toContain("second hidden quote");
  expect(host.textContent).not.toContain("first hidden quote");
  act(() =>
    editor.props.onEdit({
      updated_src: { ...editor.props.src, finding: "not_found" },
    })
  );
  expect(host.textContent).not.toContain("hidden quote");
  act(() =>
    Array.from(host.querySelectorAll("button"))
      .find((b) => b.textContent === "Save")!
      .click()
  );
  expect(save).toHaveBeenCalledWith({
    finding: "not_found",
    rationale: "Edited",
    scoped_entries: [second],
  });
});

import { expect, it } from "vitest";
import {
  projectFindingValue,
  applyFindingJsonEdit,
} from "../src/utils/findingValue";

const quote = "The Goods remain the property of the Owner.";
const original = {
  data: {
    finding: "not_found",
    rationale: "Not sufficient.",
    evidence: [{ quote, page: 10 }],
    evidence_quote: quote,
    scoped_entries: [{ finding: "supported", evidence: [{ quote, page: 11 }] }],
  },
};

it("filters nested/legacy JSON and serialization without changing the retained response", () => {
  const before = JSON.stringify(original);
  expect(JSON.stringify(projectFindingValue(original))).not.toContain(quote);
  expect(JSON.stringify(original)).toBe(before);
  const siblings = [original, { finding: "uncertain", evidence: [{ quote }] }];
  expect(JSON.stringify(projectFindingValue(siblings)[1])).toContain(quote);
});

it("preserves hidden evidence on unrelated edits and restores it on status change", () => {
  const visible = projectFindingValue(original);
  const edited = applyFindingJsonEdit(original, {
    updated_src: {
      data: { ...visible.data, rationale: "Revised rationale" },
    },
  });
  expect(edited.data.evidence).toEqual(original.data.evidence);
  expect(edited.data.scoped_entries[0].evidence).toEqual(
    original.data.scoped_entries[0].evidence
  );
  const supported = applyFindingJsonEdit(edited, {
    updated_src: {
      data: { ...projectFindingValue(edited).data, finding: "supported" },
    },
  });
  expect(JSON.stringify(projectFindingValue(supported))).toContain(quote);
  const hidden = applyFindingJsonEdit(supported, {
    updated_src: {
      data: { ...supported.data, finding: "not_found" },
    },
  });
  expect(JSON.stringify(projectFindingValue(hidden))).not.toContain(quote);
  expect(hidden.data.evidence).toEqual(original.data.evidence);
});

it("honors explicit scope deletion without shifting hidden quotations to another entry", () => {
  const retained = {
    finding: "not_found",
    scoped_entries: [
      { scope: "first", evidence_quote: "first quote" },
      { scope: "second", evidence_quote: "second quote" },
    ],
  };
  const edited = applyFindingJsonEdit(retained, {
    type: "delete",
    namespace: ["scoped_entries"],
    name: 0,
    updated_src: {
      finding: "not_found",
      scoped_entries: [{ scope: "second" }],
    },
  });
  expect(edited.scoped_entries).toEqual([retained.scoped_entries[1]]);
});

it("uses canonical finding precedence and the typed state/value form", () => {
  expect(
    JSON.stringify(
      projectFindingValue({
        finding: "uncertain",
        state: "not_found",
        value: true,
        evidence_quote: quote,
      })
    )
  ).toContain(quote);
  expect(
    JSON.stringify(
      projectFindingValue({
        state: "not_found",
        value: true,
        evidence_quote: quote,
      })
    )
  ).not.toContain(quote);
});

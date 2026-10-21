import { MockedProvider } from "@apollo/client/testing";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExtractCellFormatter } from "../src/components/extracts/datagrid/ExtractCellFormatter";
import { FindingDetails } from "../src/components/extracts/datagrid/FindingView";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
const edit = vi.fn();

beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  edit.mockReset();
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function render(
  value: unknown,
  correctedData: unknown = null,
  readOnly = false,
  isExtractComplete = true
) {
  act(() =>
    root.render(
      <MockedProvider>
        <MemoryRouter>
          <ExtractCellFormatter
            value={value}
            cellStatus={{
              isLoading: false,
              isApproved: false,
              isRejected: false,
              isEdited: correctedData !== null,
              correctedData,
              originalData: value,
              error: null,
            }}
            cellId="cell-1"
            onApprove={() => {}}
            onReject={() => {}}
            onEdit={edit}
            readOnly={readOnly}
            isExtractComplete={isExtractComplete}
            schema={{}}
            extractIsList={false}
            row={{}}
            column={{ key: "criterion", name: "Agreement signature" }}
          />
        </MemoryRouter>
      </MockedProvider>
    )
  );
}

function click(label: string) {
  const button = Array.from(document.body.querySelectorAll("button")).find(
    (item) =>
      item.getAttribute("aria-label") === label || item.textContent === label
  );
  expect(button).toBeDefined();
  act(() => button?.click());
}

const terms = {
  finding: "supported",
  rationale: "The agreement has an owner signature field.",
  evidence_quote: '[{"quote":"Owner signature","page":2}]',
  uncertainty: "A blank field does not establish actual signing.",
};

describe("finding quotation locations", () => {
  it("omits the whole evidence section for not_found despite stale anchors and loading state", () => {
    act(() =>
      root.render(
        <FindingDetails
          value={{ ...terms, finding: "not_found", scoped_entries: [terms] }}
          evidenceAnchors={[{ quote: "Owner signature", annotationId: "old" }]}
          evidenceLoading
        />
      )
    );
    expect(host.textContent).toContain(terms.rationale);
    expect(host.textContent).not.toContain("Owner signature");
    expect(host.textContent).not.toContain("Evidence");
    expect(host.textContent).not.toContain("Loading quotation");
    expect(host.textContent).not.toContain("No quotations recorded");
    expect(host.querySelector("blockquote")).toBeNull();
  });

  it("shows a verified physical location without a discrepancy when no page was reported", () => {
    const view = vi.fn();
    act(() =>
      root.render(
        <FindingDetails
          value={{
            ...terms,
            evidence_quote: [{ quote: "Owner signature", page: null }],
          }}
          onViewQuote={view}
          evidenceAnchors={[
            {
              quote: "Owner signature",
              reportedPage: null,
              locatedPage: 3,
              status: "matched",
              annotationId: "new-future-contract-quote",
            },
          ]}
        />
      )
    );
    expect(host.textContent).toContain("Reported page unavailable");
    expect(host.textContent).toContain("Matched in parsed text on PDF page 3.");
    expect(host.textContent).not.toContain("reported page differs");
    expect(host.querySelectorAll("button")).toHaveLength(1);
    click("View quotation in PDF");
    expect(view).toHaveBeenCalledExactlyOnceWith("new-future-contract-quote");
  });

  it.each([null, 2])(
    "has no navigation or candidate controls for repeated wording (reported page %s)",
    (page) => {
      const view = vi.fn();
      act(() =>
        root.render(
          <FindingDetails
            value={terms}
            onViewQuote={view}
            evidenceAnchors={[
              {
                quote: "Repeated selected words",
                reportedPage: page,
                locatedPage: null,
                status: "ambiguous",
                annotationId: null,
              },
            ]}
          />
        )
      );
      expect(host.textContent).toContain(
        "Multiple possible source locations. No highlight."
      );
      expect(host.querySelectorAll("button")).toHaveLength(0);
      expect(view).not.toHaveBeenCalled();
    }
  );

  it("describes the parsed-text location while retaining the reported page and saved quotation", () => {
    const view = vi.fn();
    act(() =>
      root.render(
        <FindingDetails
          value={terms}
          onViewQuote={view}
          evidenceAnchors={[
            {
              quote: "Owner signature",
              reportedPage: 2,
              locatedPage: 3,
              status: "different_page",
              annotationId: "verified-quote",
            },
          ]}
        />
      )
    );
    expect(host.textContent).toContain("Reported page 2");
    expect(host.textContent).toContain(
      "Matched in parsed text on PDF page 3; the reported page differs."
    );
    expect(host.querySelector("blockquote")?.textContent).toBe(
      "Owner signature"
    );
    click("View quotation in PDF");
    expect(view).toHaveBeenCalledWith("verified-quote");
  });

  it("retains unresolved quotations without a navigation link or metadata fallback", () => {
    act(() =>
      root.render(
        <FindingDetails
          value={terms}
          onViewQuote={vi.fn()}
          evidenceAnchors={[
            {
              quote: "Unmatched selected words",
              reportedPage: 2,
              status: "unmatched",
              annotationId: null,
            },
            {
              quote: "Repeated selected words",
              reportedPage: 4,
              status: "ambiguous",
              annotationId: null,
            },
          ]}
        />
      )
    );
    expect(
      Array.from(
        host.querySelectorAll("blockquote"),
        (element) => element.textContent
      )
    ).toEqual(["Unmatched selected words", "Repeated selected words"]);
    expect(host.textContent).toContain(
      "Quotation not found in retained source. No highlight."
    );
    expect(host.textContent).toContain(
      "Multiple possible source locations. No highlight."
    );
    expect(host.querySelector("button")).toBeNull();
  });
});

describe("readable extraction findings", () => {
  it.each(["supported", "contradicted", "not_found", "uncertain"])(
    "previews %s succinctly and opens readable evidence",
    (state) => {
      render({ ...terms, finding: state });
      const label = state
        .replace(/_/g, " ")
        .replace(/^./, (first) => first.toUpperCase());
      expect(host.textContent).toContain(label);
      expect(host.textContent).toContain(terms.rationale);
      expect(host.textContent).not.toContain(terms.uncertainty);
      click(`View finding: ${label}`);
      expect(document.body.textContent).toContain("Agreement signature");
      expect(document.body.textContent).toContain(terms.uncertainty);
      if (state === "not_found") {
        expect(document.body.querySelector("blockquote")).toBeNull();
        expect(document.body.textContent).not.toContain("Owner signature");
        expect(document.body.textContent).not.toContain("Evidence");
      } else {
        expect(document.body.querySelector("blockquote")?.textContent).toBe(
          "Owner signature"
        );
        expect(document.body.textContent).toContain("Page 2");
      }
      expect(document.body.textContent).toContain("Review: Awaiting review");
      expect(document.body.textContent).not.toContain("evidence_quote");
      expect(edit).not.toHaveBeenCalled();
    }
  );

  it("renders native typed values, scoped attribution and quotations", () => {
    render({
      state: "supported",
      value: ["Difficulty reading letters"],
      note: "Consumer-attributed report.",
      evidence: [
        { quote: "I could not read the letter", page: 3, speaker: "consumer" },
      ],
      scoped_entries: [
        {
          consumer: "consumer 1",
          period: "before notice",
          value: "Needs accessible text",
          evidence: [],
        },
      ],
    });
    expect(host.textContent).toContain("Difficulty reading letters");
    click("View finding: Supported");
    expect(document.body.textContent).toContain("Consumer-attributed report.");
    expect(document.body.textContent).toContain("Page 3 · consumer");
    expect(document.body.textContent).toContain("consumer 1");
    expect(document.body.textContent).toContain("Needs accessible text");
  });

  it.each([
    "not_reported",
    "unclear",
    "disputed",
    "not_applicable",
    "not_assessed",
  ])("preserves the domain state %s", (state) => {
    render({
      state,
      value: null,
      note: "This answer has the recorded state.",
      evidence: [],
    });
    const label = state
      .replace(/_/g, " ")
      .replace(/^./, (first) => first.toUpperCase());
    expect(host.textContent).toContain(label);
    expect(host.textContent).not.toContain("Supported");
  });

  it("uses corrected data inside the stock envelope and retains the original viewer", () => {
    render(terms, {
      data: {
        ...terms,
        finding: "contradicted",
        rationale: "Corrected assessment.",
      },
    });
    expect(host.textContent).toContain("Corrected assessment.");
    expect(host.textContent).not.toContain(terms.rationale);
    click("View finding: Contradicted");
    expect(document.body.textContent).toContain("Edited");
  });

  it("makes JSON editing an explicit action after the readable view", () => {
    render(terms);
    click("View finding: Supported");
    expect(document.body.textContent).not.toContain("Edit JSON Data");
    click("Edit data");
    expect(document.body.textContent).toContain("Edit JSON Data");
    expect(document.body.textContent).toContain("evidence_quote");
    click("View finding");
    expect(document.body.textContent).not.toContain("evidence_quote");
    expect(edit).not.toHaveBeenCalled();
  });

  it("keeps inspection available without edit callbacks for a read-only cell", () => {
    render(terms, null, true);
    click("View finding: Supported");
    click("View data");
    expect(
      document.body.querySelectorAll(".edit-icon, .object-add, .object-remove")
        .length
    ).toBe(0);
    expect(edit).not.toHaveBeenCalled();
  });

  it("opens completed cell details while other cells are still processing", () => {
    render(terms, null, false, false);
    click("View finding: Supported");
    expect(document.body.querySelector("blockquote")?.textContent).toBe(
      "Owner signature"
    );
    click("View data");
    expect(
      document.body.querySelectorAll(".edit-icon, .object-add, .object-remove")
        .length
    ).toBe(0);
    expect(
      document.body.querySelector('button[aria-label="Approve"]')
    ).toBeNull();
    expect(edit).not.toHaveBeenCalled();
  });

  it("distinguishes malformed evidence from an empty list", () => {
    render({ ...terms, evidence_quote: "broken JSON" });
    click("View finding: Supported");
    expect(document.body.textContent).toContain("Evidence could not be read");
    expect(document.body.textContent).not.toContain("No quotations recorded");
  });

  it("does not render invalid quotation pages as valid source locations", () => {
    render({ ...terms, evidence_quote: '[{"quote":"text","page":0}]' });
    click("View finding: Supported");
    expect(document.body.textContent).toContain("invalid quotation or page");
    expect(document.body.textContent).not.toContain("Page 0");
  });

  it("keeps the stock editor for unrelated structured data", () => {
    render({ amount: 500 });
    expect(host.textContent).toContain("View/Edit JSON");
    expect(host.querySelector('button[aria-label^="View finding"]')).toBeNull();
  });
});

it("renders the revised Terms schema with an unpaginated selected quote and scoped applicability", () => {
  render({
    finding: "present_blank",
    rationale: "The agreement supplies an uncompleted signature field.",
    evidence: [{ quote: "Customer signature: ______", page: null }],
    customer_purpose: "unclear",
    template_field_state: "present_blank",
    criterion_applicability: {
      status: "unknown",
      reason: "Agreement date unavailable.",
    },
  });
  click("View finding: Present blank");
  expect(document.body.querySelector("blockquote")?.textContent).toBe(
    "Customer signature: ______"
  );
  expect(document.body.textContent).toContain("Reported page unavailable");
  expect(document.body.textContent).toContain("Customer purpose");
  expect(document.body.textContent).toContain("Template field state");
  expect(document.body.textContent).toContain("Agreement date unavailable.");
  expect(document.body.textContent).not.toContain("invalid quotation");
});

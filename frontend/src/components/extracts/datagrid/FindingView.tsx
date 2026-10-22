import { isReviewerVisibleLabel } from "../../../utils/annotationVisibility";
import React from "react";
import styled from "styled-components";
import {
  isRecord,
  Finding,
  projectFindingValue,
  findingOutcome,
} from "../../../utils/findingValue";

function label(value: string): string {
  return value.replace(/_/g, " ").replace(/^./, (first) => first.toUpperCase());
}

const colors: Record<string, { color: string; background: string }> = {
  supported: { color: "#166534", background: "#dcfce7" },
  present_blank: { color: "#166534", background: "#dcfce7" },
  contradicted: { color: "#991b1b", background: "#fee2e2" },
  disputed: { color: "#991b1b", background: "#fee2e2" },
  uncertain: { color: "#92400e", background: "#fef3c7" },
  unclear: { color: "#92400e", background: "#fef3c7" },
};

function outcome(value: Finding) {
  const state =
    typeof value.finding === "string" ? value.finding : String(value.state);
  return {
    label: label(state),
    ...(Object.prototype.hasOwnProperty.call(colors, state)
      ? colors[state]
      : { color: "#475569", background: "#f1f5f9" }),
  };
}

function review(approved?: boolean, rejected?: boolean, edited?: boolean) {
  return `Review: ${
    approved ? "Approved" : rejected ? "Rejected" : "Awaiting review"
  }${edited ? " · Edited" : ""}`;
}

function summary(value: Finding): string {
  if (
    typeof value.value === "string" ||
    typeof value.value === "number" ||
    typeof value.value === "boolean"
  ) {
    return String(value.value);
  }
  if (
    Array.isArray(value.value) &&
    value.value.every((item) => typeof item === "string")
  ) {
    return value.value.join("; ");
  }
  const note = value.note ?? value.rationale;
  return typeof note === "string" ? note : "View finding details";
}

const Preview = styled.button`
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  max-width: 260px;
  padding: 0;
  background: transparent;
  border: 0;
  color: #334155;
  font: inherit;
  font-size: 12px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
  &:focus-visible {
    outline: 2px solid #2563eb;
    outline-offset: 4px;
  }
  .summary {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
    overflow-wrap: anywhere;
  }
`;

const Details = styled.div`
  color: #334155;
  line-height: 1.6;
  overflow-wrap: anywhere;
  h3 {
    font-size: 14px;
    margin: 22px 0 6px;
    color: #0f172a;
  }
  dl {
    margin: 0;
  }
  dt {
    font-weight: 600;
    margin-top: 10px;
  }
  dd {
    margin: 2px 0 0 16px;
    white-space: pre-wrap;
  }
  blockquote {
    margin: 8px 0;
    padding: 12px 16px;
    border-left: 3px solid #94a3b8;
    background: #f8fafc;
    white-space: pre-wrap;
  }
  .review {
    font-size: 12px;
    color: #64748b;
    margin-top: 8px;
  }
  .evidence-location {
    font-size: 12px;
    color: #475569;
  }
`;

function Value({ value }: { value: unknown }): React.ReactElement {
  if (value === null || value === undefined)
    return <span>No value recorded</span>;
  if (Array.isArray(value))
    return value.length ? (
      <ul>
        {value.map((item, index) => (
          <li key={index}>
            <Value value={item} />
          </li>
        ))}
      </ul>
    ) : (
      <span>None recorded</span>
    );
  if (isRecord(value))
    return (
      <dl>
        {Object.entries(value).map(([key, item]) => (
          <React.Fragment key={key}>
            <dt>{label(key)}</dt>
            <dd>
              <Value value={item} />
            </dd>
          </React.Fragment>
        ))}
      </dl>
    );
  return <span>{String(value)}</span>;
}

const QuoteButton = styled.button`
  margin-top: 8px;
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  background: #fff;
  color: #1e3a5f;
  font: inherit;
  cursor: pointer;
  &:hover {
    background: #f1f5f9;
  }
`;

function Evidence({
  value,
  anchors,
  onViewQuote,
}: {
  value: unknown;
  anchors?: unknown[];
  onViewQuote?: (annotationId: string) => void;
}) {
  let parsed: unknown = anchors ?? value;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return (
        <p>
          Evidence could not be read. The saved original is available in the
          data editor.
        </p>
      );
    }
  }
  if (!Array.isArray(parsed)) return <p>No evidence list recorded.</p>;
  if (!parsed.length) return <p>No quotations recorded.</p>;
  return (
    <>
      {parsed.map((item, index) => {
        if (
          !isRecord(item) ||
          typeof item.quote !== "string" ||
          !item.quote.trim() ||
          (!anchors &&
            item.page !== null &&
            (typeof item.page !== "number" ||
              !Number.isInteger(item.page) ||
              item.page < 1))
        ) {
          return (
            <p key={index}>
              Evidence entry {index + 1} has an invalid quotation or page.
              Inspect the saved original.
            </p>
          );
        }
        const annotationId = item.annotationId;
        return (
          <div key={index}>
            <blockquote>{item.quote}</blockquote>
            {Array.isArray(item.domainLabels) && (
              <div className="evidence-location">
                {item.domainLabels
                  .filter(
                    (entry) =>
                      isRecord(entry) &&
                      typeof entry.text === "string" &&
                      isReviewerVisibleLabel({ text: entry.text })
                  )
                  .map((entry) => (isRecord(entry) ? String(entry.text) : ""))
                  .join(" · ")}
              </div>
            )}
            <div className="evidence-location">
              {typeof (anchors ? item.reportedPage : item.page) === "number"
                ? `${anchors ? "Reported page" : "Page"} ${
                    anchors ? item.reportedPage : item.page
                  }`
                : "Reported page unavailable"}
              {typeof item.speaker === "string" ? ` · ${item.speaker}` : ""}
            </div>
            {anchors && (
              <div className="evidence-location" role="status">
                {item.status === "matched" &&
                  `Matched in parsed text on PDF page ${item.locatedPage}.`}
                {item.status === "different_page" &&
                  `Matched in parsed text on PDF page ${item.locatedPage}; the reported page differs.`}
                {item.matchType === "typography_whitespace" &&
                  " Matched with typographic or whitespace differences."}
                {item.status === "unmatched" &&
                  "Quotation not found in retained source. No highlight."}
                {item.status === "ambiguous" &&
                  "Multiple possible source locations. No highlight."}
                {item.status === "source_unavailable" &&
                  "Retained source coordinates are unavailable. No highlight."}
                {item.status === "projection_unavailable" &&
                  "The complete quotation could not be highlighted. No highlight."}
              </div>
            )}
            {anchors &&
              isRecord(item.scope) &&
              Object.keys(item.scope).length > 0 && (
                <Value value={item.scope} />
              )}
            {typeof annotationId === "string" && onViewQuote && (
              <QuoteButton
                type="button"
                onClick={() => onViewQuote(annotationId)}
              >
                View quotation in PDF
              </QuoteButton>
            )}
          </div>
        );
      })}
    </>
  );
}

interface FindingProps {
  value: Finding;
  summaryOnly?: boolean;
  isApproved?: boolean;
  isRejected?: boolean;
  isEdited?: boolean;
  evidenceAnchors?: unknown[];
  evidenceLoading?: boolean;
  evidenceError?: string | null;
  onRetryEvidence?: () => void;
  onViewQuote?: (annotationId: string) => void;
}

export function FindingPreview({
  value,
  isApproved,
  isRejected,
  isEdited,
  onOpen,
}: FindingProps & { onOpen: () => void }) {
  const result = outcome(value);
  return (
    <Preview
      type="button"
      onClick={onOpen}
      aria-label={`View finding: ${result.label}`}
      title={`${result.label}\n${summary(value)}\n${review(
        isApproved,
        isRejected,
        isEdited
      )}`}
    >
      <span
        style={{
          color: result.color,
          background: result.background,
          borderRadius: 12,
          padding: "2px 8px",
          fontWeight: 600,
        }}
      >
        {result.label}
      </span>
      <span className="summary">{summary(value)}</span>
    </Preview>
  );
}

export function FindingDetails({
  value,
  summaryOnly = false,
  isApproved,
  isRejected,
  isEdited,
  evidenceAnchors,
  evidenceLoading,
  evidenceError,
  onRetryEvidence,
  onViewQuote,
}: FindingProps) {
  const suppressed = findingOutcome(value) === "not_found";
  value = projectFindingValue(value);
  const result = outcome(value);
  const evidenceKey = "evidence" in value ? "evidence" : "evidence_quote";
  return (
    <Details className={summaryOnly ? "finding-summary" : undefined}>
      <span
        className={summaryOnly ? "finding-verdict" : undefined}
        style={{
          color: result.color,
          background: result.background,
          borderRadius: 12,
          padding: "4px 10px",
          fontWeight: 600,
        }}
      >
        {result.label}
      </span>
      {!summaryOnly && (
        <div className="review">{review(isApproved, isRejected, isEdited)}</div>
      )}
      {summaryOnly ? (
        <section>
          <h3>Rationale</h3>
          <Value value={value.rationale ?? value.note} />
        </section>
      ) : (
        Object.entries(value)
          .filter(([key]) => !["finding", "state", evidenceKey].includes(key))
          .map(([key, item]) => (
            <section key={key}>
              <h3>{label(key)}</h3>
              <Value value={item} />
            </section>
          ))
      )}
      {!summaryOnly && !suppressed && (
        <section>
          <h3>Evidence</h3>
          {evidenceLoading ? (
            <p role="status">Loading quotation locations…</p>
          ) : evidenceError ? (
            <div role="alert">
              <p>{evidenceError}</p>
              <QuoteButton type="button" onClick={onRetryEvidence}>
                Retry quotation locations
              </QuoteButton>
            </div>
          ) : (
            <Evidence
              value={value[evidenceKey]}
              anchors={evidenceAnchors}
              onViewQuote={onViewQuote}
            />
          )}
        </section>
      )}
    </Details>
  );
}

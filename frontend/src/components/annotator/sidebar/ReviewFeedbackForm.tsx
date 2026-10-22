import React, { useEffect, useId, useRef, useState } from "react";
import styled from "styled-components";
import { X } from "lucide-react";
import { findingFrom, projectFindingValue } from "../../../utils/findingValue";
import {
  readReviewerFeedback,
  ReviewerFeedback,
  withReviewerFeedback,
  reviewQuotations,
  rejectReviewQuotation,
  ReviewQuotation,
  ReviewSaveOptions,
} from "../../../utils/reviewerFeedback";
import { QuotationReviewList } from "./QuotationReviewList";
import { FindingDetails } from "../../extracts/datagrid/FindingView";

interface ReviewFeedbackFormProps {
  value: unknown;
  comments: ReviewerFeedback;
  onChange: (comments: ReviewerFeedback) => void;
  onSave: (
    value: unknown,
    options?: ReviewSaveOptions
  ) => void | boolean | Promise<boolean>;
  onClose: () => void;
  loading: boolean;
}

export function ReviewFeedbackForm({
  value,
  comments,
  onChange,
  onSave,
  onClose,
  loading,
}: ReviewFeedbackFormProps) {
  const id = useId();
  const [tab, setTab] = useState<"verdict" | "evidence">("verdict");
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    formRef.current
      ?.querySelector<HTMLButtonElement>('[aria-selected="true"]')
      ?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, []);
  const finding = findingFrom(projectFindingValue(value));
  if (!finding) return null;
  const initial = readReviewerFeedback(value);
  const changed =
    initial.verdict !== comments.verdict ||
    initial.evidence !== comments.evidence;
  const quotes = reviewQuotations(value);
  const handleRejectQuotation = async (quotation: ReviewQuotation) => {
    const corrected = rejectReviewQuotation(value, quotation);
    if (corrected === value) return false;
    const result = await onSave(corrected, {
      keepOpen: true,
      successMessage: "Quotation rejected.",
    });
    return result !== false;
  };
  const supporting = (
    <details className="review-quotations" open>
      <summary>
        Supporting quotations{quotes.length ? ` (${quotes.length})` : ""}
      </summary>
      <QuotationReviewList
        quotes={quotes}
        loading={loading}
        onReject={handleRejectQuotation}
      />
    </details>
  );
  const verdictContext = <FindingDetails value={finding} summaryOnly />;
  const field = (kind: "verdict" | "evidence") => (
    <div className="review-comment-field">
      <label htmlFor={`${id}-${kind}`}>
        {kind === "verdict" ? "Verdict comment" : "Evidence comment"}
      </label>
      <textarea
        id={`${id}-${kind}`}
        value={comments[kind]}
        disabled={loading}
        maxLength={10000}
        onChange={(event) =>
          onChange({ ...comments, [kind]: event.target.value })
        }
        placeholder={
          kind === "verdict"
            ? "What is right or needs to change about this verdict?"
            : "Comment on the quotations, missing evidence or source locations."
        }
      />
    </div>
  );
  return (
    <FeedbackForm
      ref={formRef}
      className="review-feedback"
      role="dialog"
      aria-modal="true"
      aria-labelledby={`${id}-title`}
      aria-busy={loading}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !loading) {
          event.stopPropagation();
          onClose();
        }
        if (event.key === "Tab") {
          const focusable = formRef.current?.querySelectorAll<HTMLElement>(
            'button:not([disabled]):not([tabindex="-1"]), textarea:not([disabled])'
          );
          const first = focusable?.[0];
          const last = focusable?.[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (!loading && changed) onSave(withReviewerFeedback(value, comments));
      }}
    >
      <header className="review-heading">
        <h2 id={`${id}-title`}>Review extraction</h2>
        <p>Comment on the verdict and its supporting evidence.</p>
        <button
          type="button"
          className="review-close"
          aria-label="Close review comments"
          disabled={loading}
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </header>
      <>
        <div className="review-tabs" role="tablist" aria-label="Review topic">
          {(["verdict", "evidence"] as const).map((topic) => (
            <button
              key={topic}
              type="button"
              role="tab"
              id={`${id}-tab-${topic}`}
              aria-selected={tab === topic}
              aria-controls={`${id}-panel`}
              tabIndex={tab === topic ? 0 : -1}
              disabled={loading}
              onClick={() => setTab(topic)}
              onKeyDown={(event) => {
                if (
                  ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
                ) {
                  event.preventDefault();
                  const next =
                    event.key === "Home"
                      ? "verdict"
                      : event.key === "End"
                      ? "evidence"
                      : tab === "verdict"
                      ? "evidence"
                      : "verdict";
                  setTab(next);
                  document.getElementById(`${id}-tab-${next}`)?.focus();
                }
              }}
            >
              {topic === "verdict" ? "Verdict" : "Evidence"}
            </button>
          ))}
        </div>
        <section
          id={`${id}-panel`}
          role="tabpanel"
          aria-labelledby={`${id}-tab-${tab}`}
          className="review-focused-panel"
        >
          {tab === "verdict" ? verdictContext : supporting}
          {field(tab)}
        </section>
      </>
      <footer className="review-actions">
        <span className="review-save-note">
          Comments are saved with this extraction.
        </span>
        {tab === "verdict" && (
          <button
            type="button"
            className="review-next"
            disabled={loading}
            onClick={() => setTab("evidence")}
          >
            Next: evidence
          </button>
        )}
        <button type="button" disabled={loading} onClick={onClose}>
          Cancel
        </button>
        <button
          type="submit"
          className="review-save"
          disabled={loading || !changed}
        >
          {loading ? "Saving…" : "Save comments"}
        </button>
      </footer>
    </FeedbackForm>
  );
}

const FeedbackForm = styled.form`
  color: #334155;
  font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  min-width: 0;
  * {
    box-sizing: border-box;
  }
  .review-heading {
    position: relative;
    padding-right: 32px;
    margin-bottom: 24px;
  }
  h2 {
    margin: 0 0 6px;
    color: #0f172a;
    font-size: 22px;
    font-weight: 600;
    line-height: 1.3;
  }
  .review-heading p {
    margin: 0;
    color: #475569;
  }
  button,
  textarea {
    font: inherit;
  }
  button {
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 14px;
    color: #334155;
    background: #fff;
    cursor: pointer;
  }
  button:hover:not(:disabled) {
    background: #f1f5f9;
  }
  button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  button:focus-visible,
  textarea:focus-visible,
  summary:focus-visible {
    outline: 2px solid #0f766e;
    outline-offset: 3px;
  }
  .review-close {
    position: absolute;
    right: -8px;
    top: -8px;
    display: inline-flex;
    padding: 8px;
    border: 0;
  }
  .review-focused-panel {
    display: grid;
    gap: 20px;
    min-width: 0;
  }
  .finding-summary {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    font: inherit;
  }
  .finding-verdict {
    display: inline-flex;
    max-width: 100%;
    font-size: 13px;
    line-height: 1.4;
  }
  .finding-summary h3 {
    margin: 0 0 4px;
    color: #475569;
    font-size: 13px;
    font-weight: 600;
  }
  .review-comment-field {
    display: grid;
    gap: 6px;
    min-width: 0;
    color: #1e293b;
  }
  .review-comment-field > label {
    font-size: 13px;
    font-weight: 600;
  }
  textarea {
    display: block;
    width: 100%;
    min-height: 136px;
    resize: vertical;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 10px 12px;
    background: #fff;
    color: #1e293b;
    line-height: 1.6;
    caret-color: #0f766e;
  }
  textarea::placeholder {
    color: #64748b;
  }
  textarea:disabled {
    background: #f8fafc;
  }
  textarea::selection {
    background: #ccfbf1;
    color: #134e4a;
  }
  .review-quotations {
    min-width: 0;
  }
  .review-quotations summary {
    width: fit-content;
    padding: 4px 0;
    color: #0f766e;
    font-weight: 600;
    cursor: pointer;
  }
  blockquote {
    margin: 12px 0 0;
    padding: 12px;
    background: #f8fafc;
    border-radius: 6px;
    overflow-wrap: anywhere;
  }
  blockquote p {
    margin: 0 0 6px;
  }
  cite,
  .review-muted,
  .review-save-note {
    color: #475569;
    font-size: 12px;
    font-style: normal;
  }
  .review-tabs {
    display: flex;
    gap: 8px;
    padding-bottom: 16px;
    margin-bottom: 20px;
    border-bottom: 1px solid #e2e8f0;
  }
  .review-tabs [aria-selected="true"] {
    background: #f0fdfa;
    color: #115e59;
    border-color: #0f766e;
  }
  .review-actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid #e2e8f0;
  }
  .review-save-note {
    margin-right: auto;
    max-width: 24ch;
  }
  .review-save {
    color: #fff;
    background: #0f766e;
    border-color: #0f766e;
  }
  .review-save:hover:not(:disabled) {
    background: #0d6860;
    border-color: #0d6860;
  }
  .review-next {
    border: 0;
    color: #0f766e;
  }
  @media (max-width: 640px) {
    .review-save-note {
      flex-basis: 100%;
      max-width: none;
      margin-bottom: 4px;
    }
  }
`;

import React, { useId, useRef, useState } from "react";
import styled from "styled-components";
import { ReviewQuotation } from "../../../utils/reviewerFeedback";

interface QuotationReviewListProps {
  quotes: ReviewQuotation[];
  onReject: (quotation: ReviewQuotation) => Promise<boolean>;
  loading: boolean;
}

export function QuotationReviewList({
  quotes,
  onReject,
  loading,
}: QuotationReviewListProps) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const [pending, setPending] = useState<ReviewQuotation | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [error, setError] = useState("");
  const busy = loading || rejecting;
  const cancel = () => {
    setPending(null);
    setError("");
    requestAnimationFrame(() => {
      if (trigger.current?.isConnected) trigger.current.focus();
    });
  };
  const confirm = async () => {
    if (!pending || busy) return;
    setRejecting(true);
    setError("");
    try {
      if (await onReject(pending)) {
        setPending(null);
        requestAnimationFrame(() => {
          const next = root.current?.querySelector<HTMLButtonElement>(
            "button.quote-reject:not([disabled])"
          );
          const field = root.current
            ?.closest("form")
            ?.querySelector<HTMLTextAreaElement>("textarea");
          (next ?? field)?.focus();
        });
      } else setError("The quotation could not be rejected. Please try again.");
    } catch {
      setError("The quotation could not be rejected. Please try again.");
    } finally {
      setRejecting(false);
    }
  };
  const confirmation = pending && (
    <div
      className="quote-confirm"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={`${id}-confirm-title`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          event.preventDefault();
          if (!busy) cancel();
        }
        if (event.key === "Tab") {
          event.stopPropagation();
          const buttons =
            event.currentTarget.querySelectorAll<HTMLButtonElement>(
              "button:not([disabled])"
            );
          if (event.shiftKey && document.activeElement === buttons[0]) {
            event.preventDefault();
            buttons[buttons.length - 1]?.focus();
          } else if (
            !event.shiftKey &&
            document.activeElement === buttons[buttons.length - 1]
          ) {
            event.preventDefault();
            buttons[0]?.focus();
          }
        }
      }}
    >
      <div className="quote-confirm-content">
        <h3 id={`${id}-confirm-title`}>Reject this quotation?</h3>
        <p>
          It will be removed from this evidence list and the extract
          annotations.
        </p>
        <blockquote>
          <p>{pending.quote}</p>
        </blockquote>
        {error && (
          <p className="quote-error" role="alert">
            {error}
          </p>
        )}
        <div className="quote-confirm-actions">
          <button type="button" disabled={busy} onClick={cancel}>
            Keep quotation
          </button>
          <button
            type="button"
            className="quote-confirm-reject"
            disabled={busy}
            onClick={() => void confirm()}
          >
            {rejecting ? "Rejecting…" : "Confirm rejection"}
          </button>
        </div>
      </div>
    </div>
  );
  return (
    <QuoteList ref={root} className="quote-review">
      {quotes.length ? (
        quotes.map((item) => (
          <article
            key={`${item.index}:${item.quote}`}
            className="quote-entry"
            aria-busy={busy}
          >
            <blockquote>
              <p>{item.quote}</p>
              <cite>
                {item.page !== null && item.page > 0
                  ? `Reported page ${item.page}`
                  : "Page not recorded"}
              </cite>
            </blockquote>
            <button
              type="button"
              className="quote-reject"
              aria-label={`Reject quotation ${item.index + 1}`}
              disabled={busy}
              onClick={(event) => {
                trigger.current = event.currentTarget;
                setPending(item);
                setError("");
                requestAnimationFrame(() =>
                  root.current
                    ?.querySelector<HTMLButtonElement>(".quote-confirm button")
                    ?.focus()
                );
              }}
            >
              Reject quotation
            </button>
          </article>
        ))
      ) : (
        <p className="review-muted" role="status">
          No supporting quotations remain.
        </p>
      )}
      {confirmation}
    </QuoteList>
  );
}

const QuoteList = styled.div`
  display: grid;
  gap: 14px;
  min-width: 0;
  .quote-entry {
    min-width: 0;
    position: relative;
  }
  blockquote {
    margin: 0;
    font-size: 14px;
  }
  .quote-reject {
    margin-top: 8px;
    color: #991b1b;
    border-color: #cbd5e1;
    font-size: 13px;
  }
  .quote-reject:hover:not(:disabled) {
    color: #7f1d1d;
    background: #fef2f2;
  }
  .quote-confirm h3 {
    margin: 0 0 6px;
    font-size: 15px;
    color: #0f172a;
  }
  .quote-confirm p {
    margin: 0 0 12px;
  }
  .quote-confirm-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }
  .quote-confirm-reject {
    color: #fff;
    background: #991b1b;
    border-color: #991b1b;
  }
  .quote-confirm-reject:hover:not(:disabled) {
    background: #7f1d1d;
    border-color: #7f1d1d;
  }
  .quote-error {
    color: #991b1b;
  }
  .quote-confirm {
    position: fixed;
    inset: 0;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    padding: 16px;
    border: 0;
    border-radius: 0;
    background: rgba(15, 23, 42, 0.4);
  }
  .quote-confirm .quote-confirm-content {
    width: 440px;
    max-width: 100%;
    max-height: calc(100dvh - 48px);
    overflow: auto;
    background: #fff;
    padding: 24px;
    border-radius: 12px;
    box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
  }
`;

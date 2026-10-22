import { findingFrom, isRecord, projectFindingValue } from "./findingValue";

export interface ReviewSaveOptions {
  keepOpen?: boolean;
  successMessage?: string;
}

export interface ReviewQuotation {
  index: number;
  quote: string;
  page: number | null;
}

export function reviewQuotations(value: unknown): ReviewQuotation[] {
  const finding = findingFrom(projectFindingValue(value));
  let evidence: unknown = finding?.evidence ?? finding?.evidence_quote;
  if (typeof evidence === "string") {
    try {
      evidence = JSON.parse(evidence);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(evidence)) return [];
  return evidence.flatMap((item, index) =>
    isRecord(item) && typeof item.quote === "string" && item.quote.trim()
      ? [
          {
            index,
            quote: item.quote,
            page: typeof item.page === "number" ? item.page : null,
          },
        ]
      : []
  );
}

/** Keep reviewer metadata outside the workflow's schema-validated response. */
export function reviewEnvelope(value: unknown): Record<string, unknown> {
  const outer: Record<string, unknown> =
    isRecord(value) && "data" in value ? { ...value } : { data: value };
  const body = outer.data;
  if (isRecord(body) && isRecord(body.reviewer_feedback)) {
    const { reviewer_feedback: legacy, ...finding } = body;
    return {
      ...outer,
      data: finding,
      reviewer_feedback: {
        ...legacy,
        ...(isRecord(outer.reviewer_feedback) ? outer.reviewer_feedback : {}),
      },
    };
  }
  return outer;
}

/** Correct the effective quotation list; the original extraction stays in cell.data. */
export function rejectReviewQuotation(
  value: unknown,
  target: ReviewQuotation
): unknown {
  const envelope = reviewEnvelope(value);
  const finding = findingFrom(envelope);
  if (!finding) return value;
  const field = "evidence" in finding ? "evidence" : "evidence_quote";
  let evidence: unknown = finding[field];
  const encoded = typeof evidence === "string";
  if (encoded) {
    try {
      evidence = JSON.parse(String(evidence));
    } catch {
      return value;
    }
  }
  if (!Array.isArray(evidence)) return value;
  const quote = evidence[target.index];
  if (
    !isRecord(quote) ||
    quote.quote !== target.quote ||
    (typeof quote.page === "number" ? quote.page : null) !== target.page
  )
    return value;
  const remaining = evidence.filter((_, index) => index !== target.index);
  const feedback = isRecord(envelope.reviewer_feedback)
    ? envelope.reviewer_feedback
    : {};
  const rejected = Array.isArray(feedback.rejected_quotations)
    ? feedback.rejected_quotations
    : [];
  return {
    ...envelope,
    data: {
      ...finding,
      [field]: encoded ? JSON.stringify(remaining) : remaining,
    },
    reviewer_feedback: {
      ...feedback,
      rejected_quotations: [
        ...rejected,
        {
          source_field: field,
          quotation: quote,
          rejected_at: new Date().toISOString(),
        },
      ],
    },
  };
}

export interface ReviewerFeedback {
  verdict: string;
  evidence: string;
}

export function readReviewerFeedback(value: unknown): ReviewerFeedback {
  const envelope = reviewEnvelope(value);
  const feedback = isRecord(envelope.reviewer_feedback)
    ? envelope.reviewer_feedback
    : {};
  return {
    verdict:
      typeof feedback.verdict_comment === "string"
        ? feedback.verdict_comment
        : "",
    evidence:
      typeof feedback.evidence_comment === "string"
        ? feedback.evidence_comment
        : "",
  };
}

/** Append reviewer comments without changing the governed response. */
export function withReviewerFeedback(
  value: unknown,
  comments: ReviewerFeedback
): unknown {
  const envelope = reviewEnvelope(value);
  return {
    ...envelope,
    reviewer_feedback: {
      ...(isRecord(envelope.reviewer_feedback)
        ? envelope.reviewer_feedback
        : {}),
      verdict_comment: comments.verdict,
      evidence_comment: comments.evidence,
    },
  };
}

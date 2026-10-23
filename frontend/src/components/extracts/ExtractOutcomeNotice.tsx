import type { DatacellType, ExtractType } from "../../types/graphql-api";
import { getExtractOutcomeSummary } from "../../utils/extractUtils";

interface ExtractOutcomeNoticeProps {
  cells: DatacellType[];
  expectedFields: number;
  extract: ExtractType;
  failedFields: number;
  isFailed: boolean;
}

/** The same terminal outcome and recovery guidance in every extract detail. */
export function ExtractOutcomeNotice({
  cells,
  expectedFields,
  extract,
  failedFields,
  isFailed,
}: ExtractOutcomeNoticeProps) {
  return (
    <div role="status">
      <strong>
        {getExtractOutcomeSummary(cells, expectedFields, extract)}
      </strong>
      {(isFailed || failedFields > 0) && (
        <p>
          This run ended with errors and {failedFields} failed field(s). Saved
          results remain available for review. Check the configuration and use
          Iterations to create a new run.
        </p>
      )}
    </div>
  );
}

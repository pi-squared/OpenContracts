import {
  projectFindingValue,
  findingFrom,
  findingOutcome,
} from "../../../utils/findingValue";
import { useLocation } from "react-router-dom";
import { useEvidenceFocus } from "../../../hooks/useEvidenceFocus";
import { isReviewerVisibleLabel } from "../../../utils/annotationVisibility";
import React, { useState } from "react";
import { FindingDetails } from "../../extracts/datagrid/FindingView";
import styled, { keyframes } from "styled-components";
import { Code, Check, X, Eye, Edit3, EyeOff, Loader2 } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { LoadingOverlay } from "../../common/LoadingOverlay";
import { CellEditor } from "./CellEditor";
import { ColumnType, DatacellType } from "../../../types/graphql-api";
import { useMutation, gql } from "@apollo/client";
import {
  REQUEST_APPROVE_DATACELL,
  REQUEST_REJECT_DATACELL,
  RequestApproveDatacellInputType,
  RequestApproveDatacellOutputType,
  RequestRejectDatacellInputType,
  RequestRejectDatacellOutputType,
  REQUEST_EDIT_DATACELL,
  RequestEditDatacellOutputType,
  RequestEditDatacellInputType,
} from "../../../graphql/mutations";
import { HighlightItem } from "./HighlightItem";
import {
  displayAnnotationOnAnnotatorLoad,
  onlyDisplayTheseAnnotations,
} from "../../../graphql/cache";
import { toast } from "react-toastify";
import { convertToServerAnnotation } from "../../../utils/transform";
import { useAnalysisManager } from "../hooks/AnalysisHooks";

// Read the presentation projection; review/edit operations retain the original data.
function InlineResultValue({
  value,
  isApproved,
  isRejected,
  isEdited,
  evidenceAnchors,
  onViewQuote,
}: {
  value: unknown;
  isApproved: boolean;
  isRejected: boolean;
  isEdited: boolean;
  evidenceAnchors?: unknown[];
  onViewQuote?: (annotationId: string) => void;
}) {
  const finding = findingFrom(value);
  const label = (key: string) =>
    key
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .replace(/_/g, " ")
      .replace(/^./, (first) => first.toUpperCase());
  const readable = (item: unknown): React.ReactNode => {
    if (item === null || item === undefined || item === "")
      return <span>No value recorded</span>;
    if (typeof item === "boolean") return <span>{item ? "Yes" : "No"}</span>;
    if (Array.isArray(item))
      return item.length ? (
        <ol>
          {item.map((entry, index) => (
            <li key={index}>{readable(entry)}</li>
          ))}
        </ol>
      ) : (
        <span>None recorded</span>
      );
    if (typeof item === "object")
      return Object.keys(item).length ? (
        <dl>
          {Object.entries(item).map(([key, entry]) => (
            <React.Fragment key={key}>
              <dt>{label(key)}</dt>
              <dd>{readable(entry)}</dd>
            </React.Fragment>
          ))}
        </dl>
      ) : (
        <span>No fields recorded</span>
      );
    return <span style={{ whiteSpace: "pre-wrap" }}>{String(item)}</span>;
  };
  if (finding)
    return (
      <FindingDetails
        value={finding}
        isApproved={isApproved}
        isRejected={isRejected}
        isEdited={isEdited}
        evidenceAnchors={evidenceAnchors}
        onViewQuote={onViewQuote}
      />
    );
  return (
    <div>
      {value !== null && typeof value === "object" && !Array.isArray(value) ? (
        Object.entries(value).map(([key, item]) => (
          <section key={key}>
            <h3>{label(key)}</h3>
            {readable(item)}
          </section>
        ))
      ) : (
        <section>
          <h3>Result</h3>
          {readable(value)}
        </section>
      )}
    </div>
  );
}

interface SingleDocumentExtractResultsProps {
  datacells: DatacellType[];
  columns: ColumnType[];
}

/**
 * SingleDocumentExtractResults component displays the extraction results for a single document.
 * It renders a table with columns and their extracted data, along with any associated annotations.
 */
export const SingleDocumentExtractResults: React.FC<
  SingleDocumentExtractResultsProps
> = ({ datacells, columns }) => {
  const { focusedEvidenceId, setFocusedEvidence, navigateToEvidence } =
    useEvidenceFocus();
  // State variables
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);
  const [tryingApprove, setTryingApprove] = useState(false);
  const [tryingReject, setTryingReject] = useState(false);
  const [annotationVisibility, setAnnotationVisibility] = useState<{
    [key: string]: boolean;
  }>({});
  const [isEditing, setIsEditing] = useState(false);
  const [editingCell, setEditingCell] = useState<DatacellType | null>(null);

  const [requestApprove] = useMutation<
    RequestApproveDatacellOutputType,
    RequestApproveDatacellInputType
  >(REQUEST_APPROVE_DATACELL);

  const [requestReject] = useMutation<
    RequestRejectDatacellOutputType,
    RequestRejectDatacellInputType
  >(REQUEST_REJECT_DATACELL);

  const [updateDatacell, { loading: updatingDatacell }] = useMutation<
    RequestEditDatacellOutputType,
    RequestEditDatacellInputType
  >(REQUEST_EDIT_DATACELL, {
    update(cache, { data }) {
      if (data?.editDatacell?.obj) {
        const updatedCell = data.editDatacell.obj;

        cache.writeFragment({
          id: `DatacellType:${updatedCell.id}`,
          fragment: gql`
            fragment UpdatedDatacell on DatacellType {
              id
              data
              correctedData
              # Include other fields if necessary
            }
          `,
          data: updatedCell,
        });
      }
    },
  });

  const {
    dataCells,
    setDataCells,
    extractResultsLoading,
    extractResultsError,
    retryExtractResults,
  } = useAnalysisManager();

  const lastCells = dataCells.length ? dataCells : datacells;
  const location = useLocation();
  const inspection = new URLSearchParams(location.search);
  const originalCellId =
    inspection.get("findingVersion") === "original"
      ? inspection.get("findingCell")
      : null;
  const retainedValue = (cell: DatacellType) => {
    const value = cell.correctedData ?? cell.data;
    return value?.data ?? value;
  };
  const valueForInspection = (cell: DatacellType) => {
    const value =
      cell.id === originalCellId ? cell.data : cell.correctedData ?? cell.data;
    return projectFindingValue(value?.data ?? value);
  };

  /**
   * Toggles the visibility of annotations under a cell.
   * @param cellId - The ID of the datacell.
   */
  const toggleAnnotationVisibility = (cellId: string) => {
    setAnnotationVisibility((prevState) => ({
      ...prevState,
      [cellId]: !prevState[cellId],
    }));
  };

  /**
   * Gets the status color for a datacell based on its approval status.
   * @param cell - The datacell to get the status color for.
   * @returns The color representing the cell's status.
   */
  const getStatusColor = (cell: DatacellType): string => {
    if (cell.approvedBy) return "rgba(76, 175, 80, 0.05)"; // Light Green
    if (cell.rejectedBy) return "rgba(244, 67, 54, 0.05)"; // Light Red
    if (cell.correctedData) return "rgba(33, 150, 243, 0.05)"; // Light Blue
    return "transparent"; // Default
  };

  /**
   * Handles approving a datacell.
   * @param cell - The datacell to approve.
   */
  const handleApprove = (cell: DatacellType) => {
    setTryingApprove(true);

    requestApprove({ variables: { datacellId: cell.id } })
      .then((response) => {
        // Review responses omit source projections; retain the loaded evidence.
        const updatedCell = response.data?.approveDatacell?.obj;

        if (updatedCell) {
          setDataCells((prev) =>
            prev.map((c) =>
              c.id === updatedCell.id ? { ...c, ...updatedCell } : c
            )
          );
          toast.success("Cell approved successfully.");
        } else {
          toast.error("Failed to approve cell.");
        }
      })
      .catch(() => toast.error("Failed to approve cell."))
      .finally(() => setTryingApprove(false));
  };

  /**
   * Handles rejecting a datacell.
   * @param cell - The datacell to reject.
   */
  const handleReject = (cell: DatacellType) => {
    setTryingReject(true);

    requestReject({ variables: { datacellId: cell.id } })
      .then((response) => {
        // Review responses omit source projections; retain the loaded evidence.
        const updatedCell = response.data?.rejectDatacell?.obj;

        if (updatedCell) {
          setDataCells((prev) =>
            prev.map((c) =>
              c.id === updatedCell.id ? { ...c, ...updatedCell } : c
            )
          );
          toast.success("Cell rejected successfully.");
        } else {
          toast.error("Failed to reject cell.");
        }
      })
      .catch(() => toast.error("Failed to reject cell."))
      .finally(() => setTryingReject(false));
  };

  /**
   * Renders the value of a datacell.
   * @param cell - The datacell to render the value for.
   * @returns The rendered value as JSX.
   */
  const renderCellValue = (cell: DatacellType) => {
    const value = valueForInspection(cell) ?? "";

    return (
      <InlineDataCell statusColor={getStatusColor(cell)}>
        <div className="inline-result-content">
          <InlineResultValue
            value={value}
            isApproved={Boolean(cell.approvedBy)}
            isRejected={Boolean(cell.rejectedBy)}
            isEdited={Boolean(cell.correctedData)}
            evidenceAnchors={cell.findingEvidence}
            onViewQuote={navigateToEvidence}
          />
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-start",
            marginTop: "8px",
          }}
        >
          <ActionButton
            className="edit"
            aria-label="Edit finding"
            disabled={cell.id === originalCellId}
            onClick={(e) => {
              e.stopPropagation();
              setEditingCell(cell);
              setIsEditing(true);
            }}
          >
            <Edit3 />
          </ActionButton>
          <ActionButton
            className="approve"
            aria-label="Approve finding"
            onClick={(e) => {
              e.stopPropagation();
              handleApprove(cell);
            }}
            disabled={Boolean(cell.approvedBy)}
          >
            <Check />
          </ActionButton>
          <ActionButton
            className="reject"
            aria-label="Reject finding"
            onClick={(e) => {
              e.stopPropagation();
              handleReject(cell);
            }}
            disabled={Boolean(cell.rejectedBy)}
          >
            <X />
          </ActionButton>
        </div>
      </InlineDataCell>
    );
  };

  const handleSave = (newValue: any) => {
    console.log("Handle save with newValue:", newValue);
    if (editingCell) {
      updateDatacell({
        variables: {
          datacellId: editingCell.id,
          editedData: { data: newValue },
        },
      })
        .then((response) => {
          const updatedCell = response.data?.editDatacell?.obj;
          if (updatedCell) {
            // Log the updated cell for debugging
            console.log("Updated Cell:", updatedCell);

            // Update the dataCells state
            setDataCells((prevCells) =>
              prevCells.map((cell) =>
                cell.id === updatedCell.id ? { ...cell, ...updatedCell } : cell
              )
            );
            toast.success("Cell updated successfully.");
            console.log("Updated Cell:", updatedCell);
            console.log("Updated dataCells:", dataCells);
          } else {
            toast.error("Failed to update cell.");
          }
        })
        .catch((error) => {
          toast.error("Error updating cell.");
          console.error(error);
        })
        .finally(() => {
          setIsEditing(false);
          setEditingCell(null);
        });
    }
  };

  console.log("Sample datacell:", dataCells[0]);

  if (extractResultsLoading) {
    return (
      <ResultsStatus role="status" aria-live="polite">
        <Spinner size={20} aria-hidden="true" />
        Loading extracts…
      </ResultsStatus>
    );
  }

  if (extractResultsError) {
    return (
      <ResultsStatus role="alert">
        <p>Could not load extract results. Please try again.</p>
        <button onClick={() => retryExtractResults().catch(() => {})}>
          Retry extracts
        </button>
      </ResultsStatus>
    );
  }

  if (lastCells.length === 0) {
    return <ResultsStatus>No extract results for this document.</ResultsStatus>;
  }

  return (
    <Container>
      <TableContainer style={{ position: "relative" }}>
        <LoadingOverlay
          active={tryingApprove || tryingReject}
          content={
            tryingApprove ? "Approving..." : tryingReject ? "Rejecting..." : ""
          }
        />

        <Table>
          <thead>
            <tr>
              <TableHeader>Column</TableHeader>
              <TableHeader>Data</TableHeader>
            </tr>
          </thead>
          <tbody>
            {columns.map((column: ColumnType) => {
              const cell = lastCells.find(
                (c) => c && c.column && c.column.id === column.id
              );
              const visibleSources =
                (findingOutcome(cell && valueForInspection(cell)) ===
                "not_found"
                  ? []
                  : cell?.fullSourceList
                )?.filter((source) =>
                  isReviewerVisibleLabel(source.annotationLabel)
                ) ?? [];
              return (
                <React.Fragment key={column.id}>
                  <TableRow
                    isHovered={hoveredRow === column.id}
                    onMouseEnter={() => setHoveredRow(column.id)}
                    onMouseLeave={() => setHoveredRow(null)}
                  >
                    <TableCell>
                      <CellContent>
                        <div
                          style={{ display: "flex", flexDirection: "column" }}
                        >
                          <span>{column.name}</span>
                          {cell && visibleSources.length > 0 && (
                            <AnnotationShield
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleAnnotationVisibility(cell.id);
                              }}
                            >
                              {annotationVisibility[cell.id] ? (
                                <Eye />
                              ) : (
                                <EyeOff />
                              )}
                              {visibleSources.length} Annotation
                              {visibleSources.length !== 1 ? "s" : ""}
                            </AnnotationShield>
                          )}
                        </div>
                        {cell && (
                          <CellStatus>
                            {cell.approvedBy && <Check color="green" />}
                            {cell.rejectedBy && (
                              <span>
                                <X color="red" aria-hidden="true" /> Rejected
                              </span>
                            )}
                            {cell.correctedData && <Code color="blue" />}
                          </CellStatus>
                        )}
                      </CellContent>
                    </TableCell>
                    <TableCell>
                      <CellContainer style={{ position: "relative" }}>
                        {cell ? renderCellValue(cell) : "-"}
                      </CellContainer>
                    </TableCell>
                  </TableRow>
                  {cell &&
                    visibleSources.length > 0 &&
                    annotationVisibility[cell.id] && (
                      <AnnotationRow>
                        <TableCell colSpan={2}>
                          <AnnotationsContainer>
                            {visibleSources.map((annotation) => (
                              <HighlightItem
                                key={annotation.id}
                                annotation={convertToServerAnnotation(
                                  annotation
                                )}
                                read_only={true}
                                relations={[]}
                                focused={focusedEvidenceId === annotation.id}
                                onInspect={() =>
                                  focusedEvidenceId === annotation.id
                                    ? setFocusedEvidence(null)
                                    : navigateToEvidence(annotation.id)
                                }
                                selectionDisplay={{
                                  showSelectedOnly: false,
                                  showBoundingBoxes: true,
                                  showStructural: false,
                                }}
                                onSelect={() => {
                                  onlyDisplayTheseAnnotations([annotation]);
                                  displayAnnotationOnAnnotatorLoad(annotation);
                                }}
                              />
                            ))}
                          </AnnotationsContainer>
                        </TableCell>
                      </AnnotationRow>
                    )}
                </React.Fragment>
              );
            })}
          </tbody>
        </Table>
      </TableContainer>

      {isEditing && editingCell && (
        <CellEditor
          value={retainedValue(editingCell) ?? ""}
          onSave={handleSave}
          onClose={() => {
            setIsEditing(false);
            setEditingCell(null);
          }}
          loading={updatingDatacell}
        />
      )}
    </Container>
  );
};

// Styled Components
const Container = styled.div`
  height: 100%;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  border: 1px solid rgba(0, 0, 0, 0.08);
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const TableContainer = styled.div`
  flex: 1;
  overflow: auto;
  margin: 0;
  background: #fff;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  table-layout: fixed;
`;

const TableHeader = styled.th`
  position: sticky;
  top: 0;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid ${OS_LEGAL_COLORS.border};
  z-index: 1;
  color: #0f172a;

  &:first-child {
    width: 200px;
  }
`;

const TableRow = styled.tr<{ isHovered: boolean }>`
  cursor: default;
  transition: background-color 0.2s ease;
  background-color: ${(props) =>
    props.isHovered ? OS_LEGAL_COLORS.surfaceHover : "#fff"};

  &:hover {
    background-color: ${OS_LEGAL_COLORS.surfaceLight};
  }

  &:last-child td {
    border-bottom: none;
  }
`;

const TableCell = styled.td`
  padding: 0;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  vertical-align: top;
`;

const CellContent = styled.div`
  display: flex;
  align-items: center;
  padding: 12px 16px;
  gap: 8px;
  min-height: 48px;
`;

interface DataCellProps {
  statusColor?: string;
}

// Update the DataCell styled component
const DataCell = styled(CellContent)<DataCellProps>`
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 16px;
  gap: 8px;
  min-height: 48px;
  background-color: ${(props) => props.statusColor || "transparent"};
  transition: background-color 0.2s ease;
`;

const InlineDataCell = styled(DataCell)`
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 10px;
  gap: 16px;
  color: #334155;
  font-size: 14px;
  line-height: 1.6;

  .inline-result-content {
    width: 100%;
    min-width: 0;
    overflow-wrap: anywhere;
    container-type: inline-size;
  }
  .inline-result-content > div {
    font: inherit;
  }
  .inline-result-content section {
    min-width: 0;
  }
  .inline-result-content h3 {
    color: #475569;
    font-size: 0.93em;
    font-weight: 600;
  }
  .inline-result-content > div > section {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
    border-top: 1px solid #e2e8f0;
    padding: 10px 0;
  }
  .inline-result-content > div > section > h3 {
    margin: 0;
  }
  .inline-result-content > div > section > h3 ~ * {
    min-width: 0;
  }
  .inline-result-content > div > section > h3 ~ div {
    grid-column: 1 / -1;
  }
  .inline-result-content dl {
    margin: 0;
  }
  .inline-result-content dt {
    font-weight: 600;
    margin-top: 8px;
    color: #475569;
  }
  .inline-result-content dd {
    margin: 2px 0 0;
    white-space: pre-wrap;
  }
  .inline-result-content ul,
  .inline-result-content ol {
    margin: 4px 0;
    padding-left: 20px;
  }
  .inline-result-content blockquote {
    border: 0;
    border-radius: 6px;
    margin: 8px 0;
    padding: 12px;
    background: #f1f5f9;
    color: #334155;
  }
  .inline-result-content .review {
    color: #475569;
    font-size: 0.86em;
    margin-top: 8px;
  }
  .inline-result-content .evidence-location {
    color: #475569;
    font-size: 0.86em;
  }
  .inline-result-content > div > section:first-of-type > span {
    color: #1e293b;
  }
  button:focus-visible {
    outline: 2px solid #0f766e;
    outline-offset: 3px;
  }

  @container (min-width: 320px) {
    .inline-result-content > div > section {
      grid-template-columns: minmax(80px, 0.65fr) minmax(0, 1.6fr);
      gap: 12px;
    }
    .inline-result-content > div > section > h3 ~ div {
      grid-column: 2;
    }
  }
`;

const CellContainer = styled.div`
  position: relative;
  width: 100%;
  min-height: 50px;
  display: flex;
  align-items: center;
  padding: 8px 24px 8px 12px;
  font-size: 0.9rem;
  color: #334155;
  line-height: 1.5;
  background-color: inherit;
`;

const AnnotationRow = styled.tr`
  background-color: ${OS_LEGAL_COLORS.gray50};
`;

const AnnotationsContainer = styled.div`
  padding: 8px 16px;
  background-color: ${OS_LEGAL_COLORS.gray50};
`;

const CellStatus = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const ButtonContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.99);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 0, 0, 0.04);
  z-index: 2000; // Ensure the button container is above other elements

  .buttons {
    display: flex;
    gap: 8px;
  }

  .status-message {
    font-size: 0.75rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
    text-align: center;
    margin-top: 4px;
    font-weight: 500;
  }

  .ui.button {
    margin: 0;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 8px;
    min-width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;

    &:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
    }

    &.green {
      background: linear-gradient(
        135deg,
        ${OS_LEGAL_COLORS.green},
        ${OS_LEGAL_COLORS.success}
      );

      &:hover:not(:disabled) {
        background: linear-gradient(
          135deg,
          ${OS_LEGAL_COLORS.success},
          ${OS_LEGAL_COLORS.successHover}
        );
      }
    }

    &.red {
      background: linear-gradient(
        135deg,
        ${OS_LEGAL_COLORS.dangerBorderHover},
        ${OS_LEGAL_COLORS.danger}
      );

      &:hover:not(:disabled) {
        background: linear-gradient(
          135deg,
          ${OS_LEGAL_COLORS.danger},
          ${OS_LEGAL_COLORS.dangerHover}
        );
      }
    }
  }
`;

// Styled Button Component
const StyledButton = styled.button<{ color?: string; hoverColor?: string }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: ${({ color }) => color || OS_LEGAL_COLORS.border};
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: background-color 0.2s ease;
  margin-right: 8px;

  &:hover {
    background-color: ${({ hoverColor }) =>
      hoverColor || OS_LEGAL_COLORS.borderHover};
  }

  &:disabled {
    background-color: ${OS_LEGAL_COLORS.border};
    cursor: not-allowed;
    opacity: 0.6;
  }

  svg {
    margin-right: 4px;
  }
`;

// Annotation Shield Button
const AnnotationShield = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
  padding: 4px 8px;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: 4px;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const ActionButtonsWrapper = styled.div`
  position: absolute;
  top: -10px;
  right: 30px;
  z-index: 100;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 4px;
  padding: 8px;
  box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1);
`;

// Styled component for Edit Icon
const EditIcon = styled.button`
  position: absolute;
  top: 8px;
  left: 20px;
  background: none;
  border: none;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: rgba(59, 130, 246, 0.1);
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const ActionButton = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
  transition: all 0.2s ease;
  margin-right: 4px;

  &:hover:not(:disabled) {
    background-color: #fff;
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &.approve:hover:not(:disabled) {
    color: ${OS_LEGAL_COLORS.green};
  }

  &.reject:hover:not(:disabled) {
    color: ${OS_LEGAL_COLORS.dangerBorderHover};
  }

  &.edit:hover:not(:disabled) {
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const spin = keyframes`
  to { transform: rotate(360deg); }
`;

const Spinner = styled(Loader2)`
  animation: ${spin} 1s linear infinite;
`;

const ResultsStatus = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
  min-height: 120px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

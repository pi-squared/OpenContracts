import { isReviewerVisibleLabel } from "../../../utils/annotationVisibility";
import React, { useState, useEffect, useRef } from "react";
import { useApolloClient, useReactiveVar } from "@apollo/client";
import { GET_DATACELL_EVIDENCE } from "../../../graphql/queries";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  IconButton,
} from "@os-legal/ui";
import { Code, Check, Edit2, Eye, X as XIcon } from "lucide-react";
import { CellStatus } from "../../../types/extract-grid";
import styled from "styled-components";
import { JSONSchema7 } from "json-schema";
import { ExtractCellEditor } from "./ExtractCellEditor";
import { FindingPreview, FindingDetails } from "./FindingView";
import {
  findingFrom,
  projectFindingValue,
  applyFindingJsonEdit,
  findingOutcome,
} from "../../../utils/findingValue";
import { getDatacellOutcome } from "../../../utils/extractUtils";
import ReactJson from "react-json-view";
import { TruncatedText } from "../../widgets/data-display/TruncatedText";
import {
  displayAnnotationOnAnnotatorLoad,
  onlyDisplayTheseAnnotations,
  selectedExtract,
  userObj,
} from "../../../graphql/cache";
import {
  DatacellType,
  ExtractType,
  ServerAnnotationType,
} from "../../../types/graphql-api";
import { Z_INDEX } from "../../../assets/configurations/constants";
import { useLocation, useNavigate } from "react-router-dom";
import {
  getDocumentUrl,
  buildQueryParams,
} from "../../../utils/navigationUtils";
import {
  OS_LEGAL_COLORS,
  primaryBlueAlpha,
  folderIconAlpha,
} from "../../../assets/configurations/osLegalStyles";

const StatusDot = styled.div<{ statusColor: string }>`
  width: 12px;
  height: 12px;
  background-color: ${(props) => props.statusColor};
  border-radius: 50%;
  cursor: pointer;
  position: absolute;
  top: 8px;
  right: 8px;
  transition: all 0.2s ease;
  box-shadow: ${(props) => {
    switch (props.statusColor) {
      case OS_LEGAL_COLORS.greenMedium:
        return "0 0 0 3px rgba(16, 185, 129, 0.15)";
      case OS_LEGAL_COLORS.dangerBorderHover:
        return "0 0 0 3px rgba(248, 113, 113, 0.15)";
      case OS_LEGAL_COLORS.folderIcon:
        return `0 0 0 3px ${folderIconAlpha(0.15)}`;
      default:
        return "0 0 0 3px rgba(148, 163, 184, 0.15)";
    }
  }};

  &:hover {
    transform: scale(1.2);
    box-shadow: ${(props) => {
      switch (props.statusColor) {
        case OS_LEGAL_COLORS.greenMedium:
          return "0 0 0 4px rgba(16, 185, 129, 0.25)";
        case OS_LEGAL_COLORS.dangerBorderHover:
          return "0 0 0 4px rgba(248, 113, 113, 0.25)";
        case OS_LEGAL_COLORS.folderIcon:
          return `0 0 0 4px ${folderIconAlpha(0.25)}`;
        default:
          return "0 0 0 4px rgba(148, 163, 184, 0.25)";
      }
    }};
  }
`;

const ButtonContainer = styled.div`
  padding: 8px;

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
`;

const CellContainer = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  height: 100%;
  min-height: 45px;
  position: relative;
  transition: background-color 0.15s ease;

  .cell-loader {
    position: absolute;
    top: 2px;
    right: 2px;
    font-size: 10px;
    color: ${OS_LEGAL_COLORS.textSecondary};
    font-style: italic;
  }

  .source-feedback {
    margin-top: 4px;
    font-size: 0.75rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:hover {
    background-color: ${primaryBlueAlpha(0.05)};
  }
`;

interface ExtractCellFormatterProps {
  value: any;
  cellStatus: CellStatus | null;
  cellId: string;
  onApprove: () => void;
  onReject: () => void;
  onEdit: (cellId: string, editedData: any) => void;
  readOnly: boolean;
  isExtractComplete: boolean;
  schema: JSONSchema7;
  extractIsList: boolean;
  row: any;
  column: any;
  cell?: DatacellType;
  extract?: ExtractType;
}

/**
 * ExtractCellFormatter component displays the content of a cell in the extract data grid.
 * It handles displaying the value, editing, approving, and rejecting the cell.
 * If the cell has correctedData, it displays that instead of the original data.
 * It also provides a control to view the original value when correctedData is present.
 */
export const ExtractCellFormatter: React.FC<ExtractCellFormatterProps> = ({
  value,
  cellStatus,
  cellId,
  onApprove,
  onReject,
  onEdit,
  readOnly,
  isExtractComplete,
  schema,
  extractIsList,
  row,
  column,
  cell,
  extract,
}) => {
  const [isPopupOpen, setIsPopupOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [failureOpen, setFailureOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isOriginalModalOpen, setIsOriginalModalOpen] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);

  const cellRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const firstMenuItemRef = useRef<HTMLButtonElement>(null);
  const statusDotRef = useRef<HTMLDivElement>(null);
  const mouseLeaveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const [openedViaKeyboard, setOpenedViaKeyboard] = useState(false);
  const [cellWidth, setCellWidth] = useState<number>(0);

  const navigate = useNavigate();
  const location = useLocation();
  const client = useApolloClient();
  const user = useReactiveVar(userObj);
  const [evidence, setEvidence] = useState<Pick<
    DatacellType,
    "findingEvidence" | "fullSourceList"
  > | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [sourcesUnavailable, setSourcesUnavailable] = useState(false);
  const [evidenceIntent, setEvidenceIntent] = useState<"detail" | "sources">(
    "detail"
  );
  // No projection data enters the overview query or Apollo's shared cache.
  // Request generations also reject late responses after correction, sign-out,
  // cell reuse, dismissal or another evidence inspection.
  const evidenceGeneration = useRef(0);
  const pendingEvidence = useRef<Promise<void> | null>(null);
  const evidenceVersion = JSON.stringify([
    cellId,
    value,
    cellStatus?.correctedData,
    user?.id,
    isOriginalModalOpen,
  ]);
  useEffect(() => {
    evidenceGeneration.current += 1;
    pendingEvidence.current = null;
    setEvidence(null);
    setEvidenceLoading(false);
    setEvidenceError(null);
    setSourcesUnavailable(false);
    if (isOriginalModalOpen) void loadEvidence("detail", "original");
    else if (isModalOpen && cell?.hasFindingEvidence)
      void loadEvidence("detail");
    return () => {
      evidenceGeneration.current += 1;
    };
  }, [evidenceVersion, client]);

  useEffect(() => {
    if (cellRef.current) {
      const computedStyle = getComputedStyle(cellRef.current);
      const padding =
        parseFloat(computedStyle.paddingLeft) +
        parseFloat(computedStyle.paddingRight);
      setCellWidth(cellRef.current.offsetWidth - padding);
    }
  }, [cellRef]);

  // Clear pending mouse-leave timeout on unmount
  useEffect(() => {
    return () => {
      if (mouseLeaveTimeoutRef.current) {
        clearTimeout(mouseLeaveTimeoutRef.current);
      }
    };
  }, []);

  // Close popup on outside click or Escape key
  useEffect(() => {
    if (!isPopupOpen) {
      // Clear any pending mouse-leave timeout when popup closes
      if (mouseLeaveTimeoutRef.current) {
        clearTimeout(mouseLeaveTimeoutRef.current);
        mouseLeaveTimeoutRef.current = null;
      }
      return;
    }

    const handleClickOutside = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        setIsPopupOpen(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsPopupOpen(false);
        statusDotRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
      if (mouseLeaveTimeoutRef.current) {
        clearTimeout(mouseLeaveTimeoutRef.current);
        mouseLeaveTimeoutRef.current = null;
      }
    };
  }, [isPopupOpen]);

  // Focus the first menu item when popup opens via keyboard
  useEffect(() => {
    if (isPopupOpen && openedViaKeyboard) {
      // Use requestAnimationFrame to ensure the DOM has rendered
      requestAnimationFrame(() => {
        firstMenuItemRef.current?.focus();
        setOpenedViaKeyboard(false);
      });
    }
  }, [isPopupOpen, openedViaKeyboard]);

  const statusColor = () => {
    if (cellStatus?.isApproved) return OS_LEGAL_COLORS.greenMedium; // Modern green
    if (cellStatus?.isRejected) return OS_LEGAL_COLORS.dangerBorderHover; // Modern red
    if (cellStatus?.isEdited) return OS_LEGAL_COLORS.folderIcon; // Modern amber
    return OS_LEGAL_COLORS.textMuted; // Modern gray
  };

  const getCellBackground = () => {
    if (cellStatus?.isLoading) return primaryBlueAlpha(0.05);
    if (cellStatus?.isApproved) return OS_LEGAL_COLORS.successLight;
    if (cellStatus?.isRejected) return OS_LEGAL_COLORS.dangerLight;
    if (cellStatus?.isEdited) return folderIconAlpha(0.05);
    return "transparent";
  };

  const loadEvidence = (
    intent: "detail" | "sources",
    version: "effective" | "original" = "effective"
  ) => {
    if (
      findingOutcome(
        version === "original" ? originalValue : displayedValue
      ) === "not_found"
    ) {
      return Promise.resolve();
    }
    setEvidenceIntent(intent);
    if (pendingEvidence.current && evidenceIntent === intent) {
      return pendingEvidence.current;
    }
    const generation = ++evidenceGeneration.current;
    setEvidence(null);
    setEvidenceError(null);
    setSourcesUnavailable(false);
    setEvidenceLoading(true);
    const request = client
      .query<{
        datacell: Pick<
          DatacellType,
          "findingEvidence" | "fullSourceList"
        > | null;
      }>({
        query: GET_DATACELL_EVIDENCE,
        variables: { id: cellId, version },
        fetchPolicy: "no-cache",
        context: { queryDeduplication: false },
      })
      .then(({ data }) => {
        if (generation !== evidenceGeneration.current) return;
        if (!data.datacell) throw new Error("Source access failed");
        setEvidence(data.datacell);
        if (intent === "sources") {
          setSourcesUnavailable(
            !openSources(data.datacell.fullSourceList ?? [])
          );
          setIsModalOpen(false);
        }
      })
      .catch(() => {
        if (generation === evidenceGeneration.current) {
          setEvidenceError(
            intent === "sources"
              ? "Source locations could not be loaded. Check source access and retry."
              : "Quotation locations could not be loaded. Check source access and retry."
          );
        }
      })
      .finally(() => {
        if (generation === evidenceGeneration.current) {
          setEvidenceLoading(false);
          pendingEvidence.current = null;
        }
      });
    pendingEvidence.current = request;
    return request;
  };

  const openViewer = () => {
    setEvidenceIntent("detail");
    setShowRawJson(false);
    setIsModalOpen(true);
    if (cell?.hasFindingEvidence) void loadEvidence("detail");
  };

  const closeModal = () => {
    evidenceGeneration.current += 1;
    pendingEvidence.current = null;
    setEvidence(null);
    setEvidenceLoading(false);
    setEvidenceError(null);
    setSourcesUnavailable(false);
    setIsModalOpen(false);
  };

  const openOriginalViewer = () => {
    closeModal();
    setIsPopupOpen(false);
    setIsOriginalModalOpen(true);
  };

  const closeOriginalModal = () => {
    closeModal();
    setIsOriginalModalOpen(false);
  };

  const handleJsonEdit = (edit: any) => {
    const updatedValue = applyFindingJsonEdit(
      cellStatus?.correctedData ?? value,
      edit
    );
    onEdit(cellId, updatedValue);
  };

  const displayedValue =
    cellStatus?.correctedData != null ? cellStatus.correctedData : value;
  const originalValue = cellStatus ? cellStatus.originalData : value;
  const findingValue = findingFrom(displayedValue);

  const outcome = extract ? getDatacellOutcome(cell, extract) : null;
  const failed = Boolean(cellStatus?.error) || outcome === "failed";
  const interrupted = outcome === "interrupted";
  const hasSavedValue =
    displayedValue !== null &&
    displayedValue !== undefined &&
    displayedValue !== "";

  const displayValue = () => {
    if (outcome === "notReported" && !hasSavedValue)
      return <span>No result recorded</span>;
    if (outcome === "pending" && !hasSavedValue) return <span>Pending</span>;
    if (findingValue && !cellStatus?.isLoading) {
      return (
        <FindingPreview
          value={findingValue}
          onOpen={openViewer}
          isApproved={cellStatus?.isApproved}
          isRejected={cellStatus?.isRejected}
          isEdited={cellStatus?.isEdited}
        />
      );
    }
    if (typeof displayedValue === "object" && displayedValue !== null) {
      return (
        <div
          onClick={openViewer}
          style={{
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
          }}
        >
          <Code size={16} />
          <span style={{ marginLeft: "5px" }}>View/Edit JSON</span>
        </div>
      );
    } else {
      return <TruncatedText text={String(displayedValue)} limit={cellWidth} />;
    }
  };

  // The clicked cell owns this transition. Shared display state must never
  // navigate from every formatter subscribed to it.
  const openSources = (sources: ServerAnnotationType[]) => {
    const annotations = sources.filter((source) =>
      isReviewerVisibleLabel(source.annotationLabel)
    );
    const first = annotations[0];
    if (!first?.document || !first.corpus) return false;
    const url = getDocumentUrl(first.document, first.corpus);
    if (url === "#") return false;
    selectedExtract(extract);
    onlyDisplayTheseAnnotations(annotations);
    displayAnnotationOnAnnotatorLoad(first);
    const params = new URLSearchParams(
      buildQueryParams({
        annotationIds: annotations.map((annotation) => annotation.id),
        extractIds: extract?.id ? [extract.id] : undefined,
        showSelectedOnly: true,
        showBoundingBoxes: true,
        showStructural: false,
      })
    );
    const labelMode = new URLSearchParams(location.search).get("labels");
    if (labelMode) params.set("labels", labelMode);
    if (isOriginalModalOpen) {
      params.set("findingCell", cellId);
      params.set("findingVersion", "original");
    }
    navigate(`${url}?${params.toString()}`);
    return true;
  };

  return (
    <CellContainer ref={cellRef} style={{ background: getCellBackground() }}>
      <Modal open={failureOpen} onClose={() => setFailureOpen(false)}>
        <ModalHeader>
          {interrupted ? "Extraction interrupted" : "Extraction failed"}:{" "}
          {column.name}
        </ModalHeader>
        <ModalBody>
          <p>
            The field {column.name} {interrupted ? "was interrupted" : "failed"}{" "}
            in {extract?.name || "this extract"}.
          </p>
          <p>
            {hasSavedValue
              ? "A saved value is available below; this field did not finish successfully."
              : "No finding was produced for this field."}
          </p>
          {cell?.failed && (
            <p>Failed at {new Date(cell.failed).toLocaleString()}.</p>
          )}
          <p>
            Successful fields remain available for review. Check the extraction
            configuration, then use Iterations to create a new run. Opening this
            notice does not rerun extraction.
          </p>
        </ModalBody>
        <ModalFooter>
          <Button onClick={() => setFailureOpen(false)}>Close</Button>
        </ModalFooter>
      </Modal>
      <div style={{ minWidth: 0 }}>
        {(failed || interrupted) && (
          <div role="status">
            <strong>
              {interrupted ? "Extraction interrupted" : "Extraction failed"}
            </strong>
            <Button
              size="sm"
              variant="secondary"
              aria-label={`View failure: ${column.name}`}
              onClick={() => setFailureOpen(true)}
            >
              View failure
            </Button>
          </div>
        )}
        {(!(failed || interrupted) || hasSavedValue) && displayValue()}
        {evidenceIntent === "sources" &&
          !isModalOpen &&
          (evidenceLoading ? (
            <div className="source-feedback" role="status">
              Loading source locations…
            </div>
          ) : evidenceError ? (
            <div className="source-feedback" role="alert">
              <p>{evidenceError}</p>
              <Button size="sm" onClick={() => void loadEvidence("sources")}>
                Retry source locations
              </Button>
            </div>
          ) : sourcesUnavailable ? (
            <div className="source-feedback" role="status">
              No highlighted source available.
            </div>
          ) : null)}
      </div>
      {cellStatus?.correctedData != null && (
        <Button
          aria-label="View original"
          variant="secondary"
          size="sm"
          onClick={openOriginalViewer}
        >
          View original
        </Button>
      )}
      {cellStatus?.isLoading && <div className="cell-loader">Loading...</div>}
      {!cellStatus?.isLoading && !cellStatus?.error && isExtractComplete && (
        <>
          <StatusDot
            ref={statusDotRef}
            statusColor={statusColor()}
            onClick={() => setIsPopupOpen(!isPopupOpen)}
            role="button"
            aria-haspopup="menu"
            aria-expanded={isPopupOpen}
            aria-label="Cell status actions"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setIsPopupOpen(!isPopupOpen);
                if (!isPopupOpen) {
                  setOpenedViaKeyboard(true);
                }
              }
            }}
          />
          {isPopupOpen && (
            <div
              ref={popupRef}
              role="menu"
              aria-label="Cell actions"
              style={{
                position: "absolute",
                top: "-4px",
                right: "24px",
                zIndex: Z_INDEX.DROPDOWN,
                background: "white",
                borderRadius: "8px",
                boxShadow: "0 4px 16px rgba(0, 0, 0, 0.12)",
                border: `1px solid ${OS_LEGAL_COLORS.border}`,
              }}
              onMouseEnter={() => {
                if (mouseLeaveTimeoutRef.current) {
                  clearTimeout(mouseLeaveTimeoutRef.current);
                  mouseLeaveTimeoutRef.current = null;
                }
              }}
              onMouseLeave={() => {
                mouseLeaveTimeoutRef.current = setTimeout(
                  () => setIsPopupOpen(false),
                  300
                );
              }}
              onKeyDown={(e) => {
                const items = popupRef.current?.querySelectorAll(
                  '[role="menuitem"]:not(:disabled):not([aria-disabled="true"])'
                );
                if (!items || items.length === 0) return;
                const itemsArr = Array.from(items) as HTMLElement[];
                const currentIndex = itemsArr.indexOf(
                  document.activeElement as HTMLElement
                );

                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  const forward = e.key === "ArrowDown";
                  const nextIndex = forward
                    ? (currentIndex + 1) % itemsArr.length
                    : (currentIndex - 1 + itemsArr.length) % itemsArr.length;
                  itemsArr[nextIndex].focus();
                } else if (e.key === "Home") {
                  e.preventDefault();
                  itemsArr[0].focus();
                } else if (e.key === "End") {
                  e.preventDefault();
                  itemsArr[itemsArr.length - 1].focus();
                } else if (e.key === "Tab") {
                  e.preventDefault();
                  setIsPopupOpen(false);
                  statusDotRef.current?.focus();
                }
              }}
            >
              <ButtonContainer>
                <div className="buttons">
                  <IconButton
                    ref={firstMenuItemRef}
                    role="menuitem"
                    tabIndex={-1}
                    aria-label="Approve"
                    title="Approve"
                    size="sm"
                    onClick={() => {
                      onApprove();
                      setIsPopupOpen(false);
                    }}
                    disabled={
                      cellStatus?.isApproved || readOnly || !isExtractComplete
                    }
                    style={{
                      background: `linear-gradient(135deg, ${OS_LEGAL_COLORS.green}, ${OS_LEGAL_COLORS.success})`,
                      color: "white",
                      border: "none",
                    }}
                  >
                    <Check size={14} />
                  </IconButton>
                  <IconButton
                    role="menuitem"
                    tabIndex={-1}
                    aria-label="Edit"
                    title="Edit"
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      closeModal();
                      if (
                        typeof displayedValue === "object" &&
                        displayedValue !== null
                      ) {
                        setShowRawJson(true);
                        setIsModalOpen(true);
                      } else {
                        setIsEditing(true);
                      }
                      setIsPopupOpen(false);
                    }}
                    disabled={readOnly || !isExtractComplete}
                  >
                    <Edit2 size={14} />
                  </IconButton>
                  {findingOutcome(displayedValue) !== "not_found" && (
                    <IconButton
                      role="menuitem"
                      tabIndex={-1}
                      aria-label="View Sources"
                      title="View Sources"
                      size="sm"
                      variant="primary"
                      onClick={() => {
                        if (
                          cell?.hasFindingEvidence ||
                          (!findingValue && cell && !cell.fullSourceList)
                        ) {
                          void loadEvidence("sources");
                        } else if (cell?.fullSourceList?.length) {
                          openSources(cell.fullSourceList);
                        }
                        setIsPopupOpen(false);
                      }}
                      disabled={
                        !cell?.hasFindingEvidence &&
                        !cell?.fullSourceList?.length &&
                        (Boolean(findingValue) || !cell)
                      }
                    >
                      <Eye size={14} />
                    </IconButton>
                  )}
                  <IconButton
                    role="menuitem"
                    tabIndex={-1}
                    aria-label="Reject"
                    title="Reject"
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      onReject();
                      setIsPopupOpen(false);
                    }}
                    disabled={
                      cellStatus?.isRejected || readOnly || !isExtractComplete
                    }
                  >
                    <XIcon size={14} />
                  </IconButton>
                </div>
                {cellStatus?.isApproved && (
                  <div className="status-message">
                    Cell is currently approved
                  </div>
                )}
                {cellStatus?.isRejected && (
                  <div className="status-message">
                    Cell is currently rejected
                  </div>
                )}
                {cellStatus?.isEdited && !cellStatus?.isApproved && (
                  <div className="status-message">Cell has been edited</div>
                )}
              </ButtonContainer>
            </div>
          )}
          {isEditing && (
            <Modal open={isEditing} onClose={() => setIsEditing(false)}>
              <ModalHeader>Edit {column.name}</ModalHeader>
              <ModalBody>
                <ExtractCellEditor
                  row={row}
                  column={column}
                  onRowChange={(updatedRow: any, commitChanges?: boolean) => {
                    if (commitChanges) {
                      onEdit(cellId, updatedRow[column.key]);
                    }
                  }}
                  onClose={() => setIsEditing(false)}
                  schema={schema}
                  extractIsList={extractIsList}
                />
              </ModalBody>
            </Modal>
          )}
        </>
      )}
      <Modal open={isOriginalModalOpen} onClose={closeOriginalModal}>
        <ModalHeader>Original Value</ModalHeader>
        <ModalBody>
          {findingFrom(originalValue) ? (
            <FindingDetails
              value={findingFrom(originalValue)!}
              evidenceAnchors={evidence?.findingEvidence}
              evidenceLoading={evidenceLoading}
              evidenceError={evidenceError}
              onRetryEvidence={() => void loadEvidence("detail", "original")}
              onViewQuote={(id) => {
                const source = evidence?.fullSourceList?.find(
                  (item) => item.id === id
                );
                if (source) {
                  openSources([source]);
                  closeOriginalModal();
                }
              }}
            />
          ) : typeof originalValue === "object" && originalValue !== null ? (
            <ReactJson
              src={projectFindingValue(originalValue)}
              theme="rjv-default"
              style={{ padding: "20px" }}
              enableClipboard={false}
              displayDataTypes={false}
            />
          ) : (
            <div style={{ padding: "20px" }}>{String(originalValue)}</div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={closeOriginalModal}>
            Close
          </Button>
        </ModalFooter>
      </Modal>
      <Modal open={isModalOpen} onClose={closeModal}>
        <ModalHeader>
          {findingValue && !showRawJson ? column.name : "Edit JSON Data"}
        </ModalHeader>
        <ModalBody>
          {findingValue && !showRawJson ? (
            <FindingDetails
              value={findingValue}
              evidenceAnchors={
                evidence?.findingEvidence ?? cell?.findingEvidence
              }
              evidenceLoading={evidenceLoading}
              evidenceError={evidenceError}
              onRetryEvidence={() => void loadEvidence("detail")}
              onViewQuote={(annotationId) => {
                const source = (
                  evidence?.fullSourceList ?? cell?.fullSourceList
                )?.find((annotation) => annotation.id === annotationId);
                if (source) {
                  openSources([source]);
                  closeModal();
                }
              }}
              isApproved={cellStatus?.isApproved}
              isRejected={cellStatus?.isRejected}
              isEdited={cellStatus?.isEdited}
            />
          ) : (
            <>
              {typeof displayedValue === "object" && displayedValue !== null ? (
                <ReactJson
                  src={projectFindingValue(displayedValue)}
                  onEdit={
                    !readOnly && isExtractComplete ? handleJsonEdit : undefined
                  }
                  onAdd={
                    !readOnly && isExtractComplete ? handleJsonEdit : undefined
                  }
                  onDelete={
                    !readOnly && isExtractComplete
                      ? (edit) => handleJsonEdit({ ...edit, type: "delete" })
                      : undefined
                  }
                  theme="rjv-default"
                  style={{ padding: "20px" }}
                  enableClipboard={false}
                  displayDataTypes={false}
                />
              ) : (
                <div>{String(displayedValue)}</div>
              )}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          {findingValue && (
            <Button
              variant="secondary"
              onClick={() => setShowRawJson(!showRawJson)}
            >
              {showRawJson
                ? "View finding"
                : readOnly || !isExtractComplete
                ? "View data"
                : "Edit data"}
            </Button>
          )}
          <Button variant="secondary" onClick={closeModal}>
            Close
          </Button>
        </ModalFooter>
      </Modal>
    </CellContainer>
  );
};

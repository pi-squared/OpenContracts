import {
  ColumnType,
  DatacellType,
  DocumentType,
  ExtractType,
} from "../types/graphql-api";
import type { ExtractDataGridHandle } from "../components/extracts/datagrid/DataGrid";
import { downloadJson } from "./extractDownloads";

/** Shared lifecycle metrics for every extract detail entry point. */
export function getExtractProgress(
  rows: DocumentType[],
  columns: ColumnType[],
  cells: DatacellType[],
  complete: boolean
) {
  let completed = 0;
  let failedFields = 0;
  const terminalColumns = new Map<string, Set<string>>();
  const documentsWithResults = new Set<string>();
  for (const cell of cells) {
    if (cell.completed) completed++;
    if (cell.failed) failedFields++;
    const documentId = cell.document?.id;
    if (!documentId) continue;
    if (cell.completed) documentsWithResults.add(documentId);
    const columnId = cell.column?.id;
    if (columnId && (cell.completed || cell.failed)) {
      const columnsForDocument = terminalColumns.get(documentId) ?? new Set();
      columnsForDocument.add(columnId);
      terminalColumns.set(documentId, columnsForDocument);
    }
  }
  return {
    documents: rows.filter(
      (doc) =>
        columns.length > 0 &&
        columns.every((column) => terminalColumns.get(doc.id)?.has(column.id))
    ).length,
    columns: columns.length,
    rows: rows.filter((doc) => documentsWithResults.has(doc.id)).length,
    failedFields,
    successRate: complete
      ? `${cells.length ? Math.round((completed / cells.length) * 100) : 0}%`
      : "—",
  };
}

export function getDocumentExtractionLabel(
  doc: DocumentType,
  cells: DatacellType[],
  columnCount: number,
  started: boolean
) {
  const own = cells.filter((cell) => cell.document?.id === doc.id);
  const completed = own.filter((cell) => cell.completed).length;
  const failed = own.filter((cell) => cell.failed).length;
  return completed || failed
    ? `${completed} of ${columnCount} fields extracted${
        failed ? ` · ${failed} failed` : ""
      }`
    : started
    ? "Awaiting extraction"
    : "Not started";
}

export function getExtractExportLabel(tab: string) {
  return tab === "data"
    ? "Export Excel"
    : tab === "schema"
    ? "Export Schema JSON"
    : tab === "iterations"
    ? "Export Iterations JSON"
    : "Export";
}

/** Export the selected public tab. Callers expose any thrown failure to the user. */
export function exportExtractTab(
  tab: string,
  extract: ExtractType | null,
  columns: ColumnType[],
  grid: Pick<ExtractDataGridHandle, "exportToExcel"> | null
) {
  if (!extract)
    throw new Error("The extract is not ready. Retry after it loads.");
  if (tab === "data") {
    if (!grid)
      throw new Error("The data grid is not ready. Retry after it loads.");
    grid.exportToExcel();
  } else if (tab === "schema") {
    downloadJson(`${extract.name || "extract"}-schema.json`, {
      fieldset: extract.fieldset,
      columns,
    });
  } else if (tab === "iterations") {
    downloadJson(`${extract.name || "extract"}-iterations.json`, {
      current: extract.id,
      parent: extract.parentExtract,
      iterations: [extract, ...(extract.fullIterationList ?? [])].map(
        (run) =>
          run && {
            id: run.id,
            name: run.name,
            created: run.created,
            started: run.started,
            finished: run.finished,
            error: run.error,
            modelConfig: run.modelConfig,
            iterationAxis: run.iterationAxis,
          }
      ),
    });
  } else throw new Error("Choose Data, Schema or Iterations to export.");
}

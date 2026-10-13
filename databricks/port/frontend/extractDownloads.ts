import { strToU8, zipSync } from "fflate";
import {
  EXCEL_MAX_CELL_LENGTH,
  EXCEL_MAX_ROWS,
  EXCEL_MAX_COLUMNS,
  DOWNLOAD_URL_REVOKE_DELAY_MS,
} from "../assets/configurations/constants";

export function downloadFile(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = name.replace(/[\\/:*?"<>|]/g, "_");
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    // Leave the URL alive until the browser has admitted the download.
    setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_REVOKE_DELAY_MS);
  }
}

export function downloadJson(name: string, data: unknown) {
  downloadFile(
    name,
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
  );
}

/** A standard XLSX workbook with explicit text cells, including JSON findings. */
export function downloadExcel(name: string, rows: unknown[][]) {
  const escape = (value: unknown) => {
    const text =
      value == null
        ? ""
        : typeof value === "object"
        ? JSON.stringify(value)
        : String(value);
    if (
      text.length > EXCEL_MAX_CELL_LENGTH ||
      /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(text)
    ) {
      throw new Error(
        "A value exceeds Excel's text limits or contains unsupported characters."
      );
    }
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/\r/g, "&#13;");
  };
  if (
    rows.length > EXCEL_MAX_ROWS ||
    rows.some((row) => row.length > EXCEL_MAX_COLUMNS)
  )
    throw new Error("The extract exceeds Excel's worksheet limits.");
  const xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
  const content = `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rows
    .map(
      (row, index) =>
        `<row r="${index + 1}">${row
          .map(
            (value) =>
              `<c t="inlineStr"><is><t xml:space="preserve">${escape(
                value
              )}</t></is></c>`
          )
          .join("")}</row>`
    )
    .join("")}</sheetData></worksheet>`;
  const files = {
    "[Content_Types].xml":
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    "_rels/.rels":
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
    "xl/workbook.xml":
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Findings" sheetId="1" r:id="rId1"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels":
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    "xl/worksheets/sheet1.xml": content,
  };
  const archive = zipSync(
    Object.fromEntries(
      Object.entries(files).map(([path, value]) => [
        path,
        new Uint8Array(strToU8(xml + value)),
      ])
    )
  );
  downloadFile(
    name,
    new Blob([new Uint8Array(archive).buffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    })
  );
}

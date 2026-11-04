import React, { useMemo, useRef } from "react";
import { MockedProvider } from "@apollo/client/testing";
import { createStore, Provider, useSetAtom } from "jotai";
import { MemoryRouter } from "react-router-dom";
import type { PDFPageProxy } from "pdfjs-dist/types/src/display/api";
import { Selection } from "../src/components/annotator/display/components/Selection";
import { PDFPageInfo } from "../src/components/annotator/types/pdf";
import {
  PdfAnnotations,
  ServerTokenAnnotation,
} from "../src/components/annotator/types/annotations";
import { pdfAnnotationsAtom } from "../src/components/annotator/context/AnnotationAtoms";
import { selectedDocumentAtom } from "../src/components/annotator/context/DocumentAtom";
import { PermissionTypes } from "../src/components/types";
import {
  AnnotationLabelType,
  DocumentType,
  LabelDisplayBehavior,
  LabelType,
} from "../src/types/graphql-api";
import {
  showAnnotationBoundingBoxes,
  showAnnotationLabels,
  showSelectedAnnotationOnly,
} from "../src/graphql/cache";
import { usePdfEvidenceInteraction } from "../src/hooks/usePdfEvidenceInteraction";
import { useAnnotationLabelLayout } from "../src/hooks/useAnnotationLabelLayout";
import {
  useEvidenceFocus,
  useEvidenceFocusEscape,
} from "../src/hooks/useEvidenceFocus";

const annotations = [
  {
    id: "evidence-a",
    label: "Field A",
    bounds: { left: 150, right: 190, top: 120, bottom: 130 },
  },
  {
    id: "evidence-b",
    label: "Field B",
    bounds: { left: 146, right: 300, top: 119.75, bottom: 130.25 },
  },
].map(
  ({ id, label, bounds }) =>
    new ServerTokenAnnotation(
      0,
      {
        id: `label-${id}`,
        text: label,
        color: "#616a6b",
        labelType: LabelType.TokenLabel,
        readonly: true,
      } as AnnotationLabelType,
      "Repeated synthetic quotation",
      false,
      {
        0: { bounds, tokensJsons: [], rawText: "Repeated synthetic quotation" },
      },
      [PermissionTypes.CAN_READ],
      false,
      false,
      false,
      id,
      undefined,
      null,
      true
    )
);

function Surface({ scale }: { scale: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const pageInfo = useMemo(
    () =>
      new PDFPageInfo(
        {
          pageNumber: 1,
          getViewport: () => ({ width: 600, height: 400 }),
        } as unknown as PDFPageProxy,
        [],
        scale
      ),
    [scale]
  );
  const { focusedEvidenceId, navigateToEvidence } = useEvidenceFocus();
  const setDocument = useSetAtom(selectedDocumentAtom);
  const { mouseHandlers, hoveredEvidenceIds, activateAt } =
    usePdfEvidenceInteraction(canvas, pageInfo, annotations);
  useAnnotationLabelLayout(container, hoveredEvidenceIds, scale);
  useEvidenceFocusEscape(container);
  return (
    <>
      <button onClick={() => navigateToEvidence("evidence-a")}>
        Inspect source A
      </button>
      <button onClick={() => navigateToEvidence("evidence-b")}>
        Inspect source B
      </button>
      <button
        onClick={() =>
          setDocument({
            id: "other-document",
            pdfFileHash: "other-hash",
          } as DocumentType)
        }
      >
        Switch document
      </button>
      <output aria-label="Focused evidence">
        {focusedEvidenceId ?? "None"}
      </output>
      <div
        ref={container}
        {...mouseHandlers}
        style={{
          position: "relative",
          marginLeft: 40,
          marginTop: 160,
          width: 600 * scale,
          height: 400 * scale,
        }}
      >
        <canvas
          ref={canvas}
          width={600 * scale}
          height={400 * scale}
          style={{ display: "block", background: "#fff" }}
        />
        {annotations.map((annotation) => (
          <Selection
            key={annotation.id}
            selected={false}
            pageInfo={pageInfo}
            annotation={annotation}
            evidenceHovered={hoveredEvidenceIds.includes(annotation.id)}
            onEvidenceActivate={activateAt}
          />
        ))}
      </div>
    </>
  );
}

/** Real production selection, label/menu, focus and page-click handling on a synthetic canvas. */
export function PdfEvidenceOverlapTestWrapper({
  scale = 1,
}: {
  scale?: number;
}) {
  const store = useMemo(() => {
    const value = createStore();
    value.set(pdfAnnotationsAtom, new PdfAnnotations(annotations, [], []));
    value.set(selectedDocumentAtom, {
      id: "synthetic-document",
      pdfFileHash: "synthetic-hash",
    } as DocumentType);
    showAnnotationBoundingBoxes(true);
    showAnnotationLabels(LabelDisplayBehavior.ON_HOVER);
    showSelectedAnnotationOnly(false);
    return value;
  }, []);
  return (
    <MockedProvider>
      <Provider store={store}>
        <MemoryRouter initialEntries={["/synthetic-document"]}>
          <Surface scale={scale} />
        </MemoryRouter>
      </Provider>
    </MockedProvider>
  );
}

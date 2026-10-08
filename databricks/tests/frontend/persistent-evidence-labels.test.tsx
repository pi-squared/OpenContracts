import { ViewLabelSelector } from "../src/components/annotator/labels/view_labels_selector/ViewLabelSelector";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { pdfAnnotationsAtom } from "../src/components/annotator/context/AnnotationAtoms";
import {
  PdfAnnotations,
  RelationGroup,
} from "../src/components/annotator/types/annotations";
import { useVisibleAnnotations } from "../src/components/annotator/hooks/useVisibleAnnotations";
import { spanLabelsToViewAtom } from "../src/components/annotator/context/AnnotationControlAtoms";
import { selectedRelationsAtom } from "../src/components/annotator/context/UISettingsAtom";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { Provider, createStore } from "jotai";
import { afterEach, beforeEach, expect, it } from "vitest";
import { Selection } from "../src/components/annotator/display/components/Selection";
import { PDFPageInfo } from "../src/components/annotator/types/pdf";
import { ServerTokenAnnotation } from "../src/components/annotator/types/annotations";
import { convertToServerAnnotation } from "../src/utils/transform";
import {
  showAnnotationLabels,
  showSelectedAnnotationOnly,
  showStructuralAnnotations,
  selectedAnnotationIds,
} from "../src/graphql/cache";
import { LabelDisplayBehavior } from "../src/types/graphql-api";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  showAnnotationLabels(LabelDisplayBehavior.ON_HOVER);
  showSelectedAnnotationOnly(false);
  showStructuralAnnotations(false);
  selectedAnnotationIds([]);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  showSelectedAnnotationOnly(false);
  selectedAnnotationIds([]);
});
const page = new PDFPageInfo(
  { pageNumber: 1, getViewport: () => ({ width: 600, height: 800 }) } as any,
  [],
  1
);
const quote = convertToServerAnnotation({
  id: "quote",
  page: 0,
  rawText: "Selected quotation",
  structural: false,
  isEvidenceQuote: true,
  annotationType: "TOKEN_LABEL",
  annotationLabel: {
    id: "criterion",
    text: "Agreement signature",
    color: "#2563eb",
    labelType: "TOKEN_LABEL",
  },
  json: {
    "0": {
      bounds: { top: 100, bottom: 120, left: 50, right: 200 },
      tokensJsons: [],
    },
  },
  myPermissions: [],
} as any) as ServerTokenAnnotation;
function render(selected: boolean, scale = 1) {
  act(() =>
    root.render(
      <Provider>
        <MockedProvider>
          <MemoryRouter>
            <Selection
              selected={selected}
              pageInfo={page.withScale(scale)}
              annotation={quote.update()}
            />
          </MemoryRouter>
        </MockedProvider>
      </Provider>
    )
  );
}
function chip() {
  const text = Array.from(host.querySelectorAll("span")).find(
    (element) =>
      element.textContent === "Agreement signature" &&
      element.children.length === 0
  );
  expect(text).toBeDefined();
  return text!.parentElement!.parentElement!.parentElement!;
}
it("a domain evidence label stays visible without hover across selection and zoom transitions", () => {
  for (const [selected, scale] of [
    [false, 1],
    [true, 1],
    [false, 1.5],
    [true, 0.75],
    [false, 0.75],
  ]) {
    render(Boolean(selected), Number(scale));
    expect(getComputedStyle(chip()).display).not.toBe("none");
    expect(host.textContent).not.toContain("OC_EXTRACT_SOURCE");
  }
});
it("the label-text HIDE setting keeps evidence labels persistent", () => {
  showAnnotationLabels(LabelDisplayBehavior.HIDE);
  render(false);
  expect(getComputedStyle(chip()).display).not.toBe("none");
});
it("an explicit selected-only filter still excludes an unselected quotation", () => {
  showSelectedAnnotationOnly(true);
  render(false);
  expect(getComputedStyle(chip()).display).toBe("none");
  render(true);
  expect(getComputedStyle(chip()).display).not.toBe("none");
});

function VisibleEvidence() {
  const visible = useVisibleAnnotations();
  return (
    <>
      {visible.map((annotation) => (
        <div key={annotation.id} data-annotation-id={annotation.id}>
          <Selection
            selected
            pageInfo={page}
            annotation={annotation as ServerTokenAnnotation}
          />
        </div>
      ))}
    </>
  );
}

it.each(["quotation", "relationship"])(
  "an explicit label exclusion removes a selected %s's quotation and persistent chip until included again",
  (selection) => {
    const store = createStore();
    const relation = new RelationGroup(
      [quote.id],
      [],
      quote.annotationLabel,
      "selected-relation"
    );
    store.set(pdfAnnotationsAtom, new PdfAnnotations([quote], [relation], []));
    if (selection === "quotation") selectedAnnotationIds([quote.id]);
    else store.set(selectedRelationsAtom, [relation]);
    store.set(spanLabelsToViewAtom, [quote.annotationLabel]);
    act(() =>
      root.render(
        <Provider store={store}>
          <MockedProvider>
            <MemoryRouter>
              <VisibleEvidence />
            </MemoryRouter>
          </MockedProvider>
        </Provider>
      )
    );
    expect(host.querySelector('[data-annotation-id="quote"]')).not.toBeNull();
    expect(getComputedStyle(chip()).display).not.toBe("none");

    act(() =>
      store.set(spanLabelsToViewAtom, [
        { ...quote.annotationLabel, id: "another-label" },
      ])
    );
    expect(host.querySelector('[data-annotation-id="quote"]')).toBeNull();
    expect(host.textContent).not.toContain("Agreement signature");

    act(() => store.set(spanLabelsToViewAtom, [quote.annotationLabel]));
    expect(host.querySelector('[data-annotation-id="quote"]')).not.toBeNull();
    expect(getComputedStyle(chip()).display).not.toBe("none");
  }
);

it("reviewer label filters offer domain labels and hide the retained grounding label", () => {
  const store = createStore();
  const internal = {
    ...quote.annotationLabel,
    id: "grounding",
    text: "OC_EXTRACT_SOURCE",
  };
  store.set(corpusStateAtom, {
    ...store.get(corpusStateAtom),
    spanLabels: [internal, quote.annotationLabel],
  });
  store.set(
    pdfAnnotationsAtom,
    new PdfAnnotations(
      [quote, quote.update({ annotationLabel: internal })],
      [],
      []
    )
  );
  act(() =>
    root.render(
      <Provider store={store}>
        <MockedProvider>
          <MemoryRouter>
            <ViewLabelSelector />
          </MemoryRouter>
        </MockedProvider>
      </Provider>
    )
  );
  const control =
    host.querySelector('[role="combobox"]') ??
    host.querySelector('[aria-haspopup="listbox"]');
  expect(control).not.toBeNull();
  act(() => (control as HTMLElement).click());
  expect(document.body.textContent).toContain("Agreement signature");
  expect(document.body.textContent).not.toContain("OC_EXTRACT_SOURCE");
});

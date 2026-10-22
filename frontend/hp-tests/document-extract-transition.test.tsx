import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  Observable,
  useReactiveVar,
} from "@apollo/client";
import { Provider } from "jotai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { SelectionSetNode } from "graphql";
import { CentralRouteManager } from "../src/routing/CentralRouteManager";
import { useDocumentLoader } from "../src/components/knowledge_base/document/document_kb/useDocumentLoader";
import { useJumpToRelationship } from "../src/components/knowledge_base/document/document_kb/useJumpToRelationship";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../src/components/annotator/hooks/AnalysisHooks";
import { SingleDocumentExtractResults } from "../src/components/annotator/sidebar/SingleDocumentExtractResults";
import { ExtractDetail } from "../src/views/ExtractDetail";
import { ExtractDataGrid } from "../src/components/extracts/datagrid/DataGrid";
import { PDF } from "../src/components/annotator/renderers/pdf/PDF";
import { usePdfAnnotations } from "../src/components/annotator/hooks/AnnotationHooks";
import {
  useAnnotationControls,
  useZoomLevel,
} from "../src/components/annotator/context/UISettingsAtom";
import {
  cache,
  authStatusVar,
  authInitCompleteVar,
  openedDocument,
  openedCorpus,
  openedExtract,
  selectedExtract,
  selectedAnnotationIds,
  selectedExtractIds,
  selectedAnalysesIds,
  onlyDisplayTheseAnnotations,
  displayAnnotationOnAnnotatorLoad,
  routeLoading,
  routeError,
  showAnnotationLabels,
  showSelectedAnnotationOnly,
  showStructuralAnnotations,
} from "../src/graphql/cache";
import { LabelDisplayBehavior } from "../src/types/graphql-api";
import { updateAnnotationDisplayParams } from "../src/utils/navigationUtils";
import { navigationCircuitBreaker } from "../src/utils/navigationCircuitBreaker";

// Only byte loading/PDF decoding and browser APIs absent from jsdom are stubs.
// Both loaders, source cards, PDF annotation/focus code, routing and cache are real.
vi.mock("../src/components/annotator/api/cachedRest", () => ({
  getCachedPDFUrl: async (url: string) => url,
  getPawlsLayer: async () => [],
  getDocumentRawText: async () => "",
  getDocxBytes: async () => new Uint8Array(),
}));
vi.mock("pdfjs-dist", () => ({
  getDocument: () => ({
    promise: Promise.resolve({
      numPages: 2,
      getPage: async (pageNumber: number) => ({
        pageNumber,
        getViewport: ({ scale }: { scale: number }) => ({
          width: 600 * scale,
          height: 800 * scale,
        }),
        render: () => ({ promise: Promise.resolve(), cancel: () => {} }),
        getAnnotations: async () => [],
      }),
    }),
  }),
}));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const id = (type: string, number: number) => btoa(`${type}:${number}`);
const owner = {
  __typename: "UserType",
  id: id("UserType", 1),
  slug: "reviewer",
  username: "reviewer",
  email: "fixture@example.invalid",
};
const corpus = {
  __typename: "CorpusType",
  id: id("CorpusType", 1),
  slug: "fixtures",
  title: "Synthetic evidence",
  description: "",
  creator: owner,
  isPublic: false,
  myPermissions: ["READ"],
  labelSet: null,
};
const documents = ["a", "b"].map((name, index) => ({
  __typename: "DocumentType",
  id: id("DocumentType", index + 1),
  slug: `document-${name}`,
  title: `Document ${name.toUpperCase()}`,
  description: "",
  creator: owner,
  fileType: "application/pdf",
  pdfFile: `/fixture/${name}.pdf`,
  pdfFileHash: name,
  pawlsParseFile: `/fixture/${name}.json`,
  txtExtractFile: null,
  mdSummaryFile: null,
  created: "2026-10-06T10:00:00Z",
  backendLock: false,
  isPublic: false,
  isLatestVersion: true,
  myPermissions: ["READ"],
  allNotes: [],
  allDocRelationships: [],
}));
const column = {
  __typename: "ColumnType",
  id: id("ColumnType", 1),
  name: "Criterion",
  query: "",
  outputType: "str",
  limitToLabel: null,
  instructions: "",
  extractIsList: false,
  taskName: "fixture",
};
let extractError: string | null = null;
const extract = {
  __typename: "ExtractType",
  id: id("ExtractType", 1),
  name: "Fixture extract",
  creator: owner,
  corpus,
  fieldset: {
    __typename: "FieldsetType",
    id: id("FieldsetType", 1),
    name: "Fixture",
    description: "",
    inUse: true,
    fullColumnList: [column],
  },
  created: "2026-10-06T10:00:00Z",
  started: "2026-10-06T10:00:00Z",
  finished: "2026-10-06T10:01:00Z",
  get error() {
    return extractError;
  },
  myPermissions: ["READ"],
  corpusAction: null,
};
const analyses = [1, 2].map((number) => ({
  __typename: "AnalysisType",
  id: id("AnalysisType", number),
  analyzer: {
    __typename: "AnalyzerType",
    id: id("AnalyzerType", number),
    description: `Analysis ${number}`,
    analyzerId: `fixture-${number}`,
    fullLabelList: [],
  },
  corpusAction: null,
  annotations: { totalCount: 1 },
  analysisStarted: extract.started,
  analysisCompleted: extract.finished,
  status: "COMPLETED",
}));

function annotation(
  doc: (typeof documents)[number],
  number: number,
  text: string,
  evidence = true
) {
  return {
    __typename: "AnnotationType",
    id: id("AnnotationType", number),
    document: doc,
    corpus,
    page: number % 2,
    rawText: text,
    annotationType: "TOKEN_LABEL",
    structural: false,
    isEvidenceQuote: evidence,
    analysis: null,
    myPermissions: ["READ"],
    contentModalities: ["TEXT"],
    linkUrl: null,
    annotationLabel: {
      __typename: "AnnotationLabelType",
      id: id("AnnotationLabelType", number),
      text,
      color: "#2563eb",
      labelType: "TOKEN_LABEL",
      icon: null,
      description: "",
    },
    userFeedback: { edges: [], totalCount: 0 },
    allSourceNodeInRelationship: [],
    allTargetNodeInRelationship: [],
    json: {
      [number % 2]: {
        bounds: { left: 50, right: 200, top: 100, bottom: 120 },
        tokensJsons: [],
      },
    },
  };
}
const sources = documents.map((doc, index) => [
  annotation(doc, 11 + index * 2, `${doc.title} first quote`),
  annotation(doc, 12 + index * 2, `${doc.title} second quote`),
]);
const manual = documents.map((doc, index) =>
  annotation(doc, 21 + index, `${doc.title} manual`, false)
);
const analysisSources = analyses.map((analysis, index) => ({
  ...annotation(documents[1], 31 + index, `Analysis ${index + 1} quote`, false),
  analysis: { id: analysis.id },
}));
const relationships = documents.map((doc, index) => ({
  __typename: "RelationshipType",
  id: id("RelationshipType", index + 1),
  structural: false,
  relationshipLabel: {
    __typename: "AnnotationLabelType",
    id: id("AnnotationLabelType", 40 + index),
    text: `${doc.title} relation`,
    color: "#2563eb",
    icon: null,
    description: "",
  },
  sourceAnnotations: { edges: [{ node: { id: manual[index].id } }] },
  targetAnnotations: { edges: [{ node: { id: manual[index].id } }] },
}));
const cells = documents.map((doc, index) => ({
  __typename: "DatacellType",
  id: id("DatacellType", index + 1),
  document: doc,
  column,
  data: { data: `Finding ${index + 1}` },
  correctedData: null,
  dataDefinition: null,
  started: extract.started,
  completed: extract.finished,
  failed: null,
  stacktrace: null,
  approvedBy: null,
  rejectedBy: null,
  hasFindingEvidence: true,
  findingEvidence: [],
  fullSourceList: sources[index],
}));
const gridPath = `/e/reviewer/${extract.id}`;

// Project fixture responses to the actual requested GraphQL fields. In particular,
// do not let unsolicited source flags bypass Apollo's cache selection semantics.
function project(set: SelectionSetNode, value: any): any {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) return value.map((item) => project(set, item));
  const output: Record<string, unknown> = {};
  for (const selection of set.selections) {
    if (selection.kind !== "Field")
      throw new Error("Fixture projection expects field selections");
    const key = selection.alias?.value ?? selection.name.value;
    const field = value[selection.name.value];
    output[key] = selection.selectionSet
      ? project(selection.selectionSet, field)
      : field ?? null;
  }
  return output;
}

type Pending = {
  name: string;
  variables: Record<string, any>;
  release: () => void;
};
let pending: Pending[];
let requests: Pending[];
let host: HTMLDivElement;
let root: Root;
let client: ApolloClient<unknown>;
let scrollTargets: HTMLElement[];
let rejectedCellIds: Set<string>;
let reviewCells: any[];
let reviewColumns: any[];
const originalScrollIntoView = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "scrollIntoView"
);

function response(name: string, variables: Record<string, any>) {
  const index = documents.findIndex(
    (doc) =>
      doc.id === variables.documentId || doc.slug === variables.documentSlug
  );
  const doc = documents[index];
  if (!name)
    return {
      documents: {
        edges: [],
        totalCount: 0,
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
      },
    };
  if (name === "ResolveExtractById") return { extract };
  if (name === "GetExtract")
    return {
      extract: {
        ...extract,
        fullDocumentList: documents,
        fullDatacellList: cells,
        fullIterationList: [],
        parentExtract: null,
        modelConfig: null,
        iterationAxis: null,
        sourceReadinessError: null,
      },
    };
  if (name === "ResolveDocumentInCorpusFull")
    return { corpusBySlugs: corpus, documentInCorpusBySlugs: doc };
  if (name === "GetDocumentKnowledgeAndAnnotations")
    return {
      document: {
        ...doc,
        allAnnotations: [manual[index]],
        allRelationships: [relationships[index]],
      },
      corpus,
    };
  if (name === "GetConversations")
    return {
      conversations: {
        totalCount: 0,
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
      },
    };
  if (name === "DocumentData")
    return {
      documentCorpusActions: {
        corpusActions: [],
        extracts: [extract],
        analysisRows: analyses.map((analysis, number) => ({
          id: `row-${number}`,
          analysis,
          data: { edges: [] },
        })),
      },
    };
  if (name === "GetDatacellsForExtract")
    return {
      extract: {
        ...extract,
        fieldset: { ...extract.fieldset, fullColumnList: reviewColumns },
        fullDatacellList: reviewCells.map((cell) => ({
          ...cell,
          rejectedBy: rejectedCellIds.has(cell.id) ? owner : null,
        })),
      },
    };
  if (name === "RejectDatacell") {
    rejectedCellIds.add(variables.datacellId);
    return {
      rejectDatacell: {
        ok: true,
        message: "Rejected",
        obj: {
          ...reviewCells.find((cell) => cell.id === variables.datacellId),
          approvedBy: null,
          rejectedBy: owner,
        },
      },
    };
  }
  if (name === "GetDatacellEvidence")
    return { datacell: reviewCells.find((cell) => cell.id === variables.id) };
  if (name === "GetAnnotationsForAnalysis") {
    const number = analyses.findIndex(
      (analysis) => analysis.id === variables.analysisId
    );
    return {
      analysis: {
        ...analyses[number],
        fullAnnotationList: [analysisSources[number]],
      },
    };
  }
  if (name === "GetDocumentAnnotationsOnly") {
    const number = analyses.findIndex(
      (analysis) => analysis.id === variables.analysisId
    );
    // This is the reported backend behavior: an extract ID used as an analysis
    // filter returns an empty result without a GraphQL error.
    return {
      document: {
        id: doc.id,
        allAnnotations:
          number >= 0
            ? [analysisSources[number]]
            : variables.analysisId
            ? []
            : [manual[index]],
        allRelationships: variables.analysisId ? [] : [relationships[index]],
      },
    };
  }
  throw new Error(`Unexpected network operation ${name}`);
}

function DocumentView({ documentId }: { documentId: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const {
    dataCells,
    columns,
    extracts,
    analyses: availableAnalyses,
    onSelectExtract,
    onSelectAnalysis,
  } = useAnalysisManager();
  const { selectedAnalysis: activeAnalysis, selectedExtract: activeExtract } =
    useAnalysisSelection();
  const loader = useDocumentLoader({
    documentId,
    corpusId: corpus.id,
    authReady: true,
    zoomLevel: 1,
    setProgress: () => {},
    selectedAnalysisId: activeAnalysis?.id ?? null,
    selectedExtractId: activeExtract?.id ?? null,
  });
  const { pdfAnnotations } = usePdfAnnotations();
  const { zoomLevel, setZoomLevel } = useZoomLevel();
  const { setSpanLabelsToView } = useAnnotationControls();
  useJumpToRelationship();
  return (
    <>
      <h1>{loader.combinedData?.document?.title}</h1>
      <button
        onClick={() =>
          navigate(`/d/reviewer/fixtures/document-b?extract=${extract.id}`)
        }
      >
        Open other document
      </button>
      <button onClick={() => navigate(gridPath)}>Open extract grid</button>
      <output aria-label="Zoom">{zoomLevel}</output>
      <button onClick={() => setZoomLevel(1.5)}>Set zoom 150%</button>
      <button
        onClick={() =>
          setSpanLabelsToView(
            sources
              .flat()
              .filter((source) => !selectedAnnotationIds().includes(source.id))
              .map((source) => source.annotationLabel) as any
          )
        }
      >
        Exclude selected label
      </button>
      <button onClick={() => setSpanLabelsToView(null)}>
        Include all labels
      </button>
      <button
        onClick={() =>
          updateAnnotationDisplayParams(location, navigate, {
            showSelectedOnly: true,
          })
        }
      >
        Show selected only
      </button>
      <button
        onClick={() =>
          updateAnnotationDisplayParams(location, navigate, {
            showSelectedOnly: false,
            labelDisplay: LabelDisplayBehavior.ON_HOVER,
          })
        }
      >
        Default labels
      </button>
      {[LabelDisplayBehavior.ALWAYS, LabelDisplayBehavior.HIDE].map((mode) => (
        <button
          key={mode}
          onClick={() =>
            updateAnnotationDisplayParams(location, navigate, {
              labelDisplay: mode,
            })
          }
        >
          {mode} labels
        </button>
      ))}
      <button onClick={() => onSelectExtract(extracts[0])}>
        View fixture extract
      </button>
      <button onClick={() => onSelectAnalysis(availableAnalyses[0])}>
        View analysis 1
      </button>
      <button onClick={() => onSelectAnalysis(availableAnalyses[1])}>
        View analysis 2
      </button>
      <button onClick={() => onSelectAnalysis(null)}>
        View manual annotations
      </button>
      <button onClick={() => navigate({ search: "?rel=2" }, { replace: true })}>
        Focus manual relationship
      </button>
      <section data-testid="pdf-pane">
        <PDF
          read_only
          createAnnotationHandler={async () => {
            throw new Error("Read-only fixture");
          }}
        />
      </section>
      <section data-testid="extract-pane">
        <SingleDocumentExtractResults columns={columns} datacells={dataCells} />
      </section>
      <section aria-label="Relationships">
        {pdfAnnotations.relations.map((relation) => (
          <span key={relation.id}>{relation.label.text}</span>
        ))}
      </section>
    </>
  );
}
function Workspace() {
  const location = useLocation();
  const navigate = useNavigate();
  const doc = useReactiveVar(openedDocument);
  const loading = useReactiveVar(routeLoading);
  return location.pathname.startsWith("/d/") ? (
    doc && !loading && <DocumentView documentId={doc.id} />
  ) : (
    <>
      <button
        onClick={() =>
          navigate(`/d/reviewer/fixtures/document-a?extract=${extract.id}`)
        }
      >
        Open Document A
      </button>
      <ExtractDataGrid
        extract={extract as any}
        cells={cells as any}
        rows={documents as any}
        columns={[column] as any}
        onAddDocIds={() => {}}
        onRemoveDocIds={() => {}}
        onRemoveColumnId={() => {}}
        onAddColumn={() => {}}
      />
    </>
  );
}

beforeEach(() => {
  extractError = null;
  cache.restore({});
  pending = [];
  requests = [];
  scrollTargets = [];
  rejectedCellIds = new Set();
  reviewCells = cells;
  reviewColumns = [column];
  for (const variable of [
    openedDocument,
    openedCorpus,
    openedExtract,
    selectedExtract,
    displayAnnotationOnAnnotatorLoad,
  ])
    variable(null);
  for (const variable of [
    selectedAnnotationIds,
    selectedExtractIds,
    selectedAnalysesIds,
    onlyDisplayTheseAnnotations,
  ])
    variable([]);
  routeLoading(false);
  routeError(null);
  authStatusVar("AUTHENTICATED");
  authInitCompleteVar(true);
  showAnnotationLabels(LabelDisplayBehavior.ON_HOVER);
  showSelectedAnnotationOnly(false);
  showStructuralAnnotations(false);
  navigationCircuitBreaker.reset();
  window.history.replaceState(null, "", gridPath);
  vi.stubGlobal("CSS", {
    escape: (value: string) =>
      value.replace(/[^a-zA-Z0-9_-]/g, (character) => `\\${character}`),
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => ({ clearRect() {} } as any)
  );
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: function (this: HTMLElement) {
      scrollTargets.push(this);
    },
  });
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  client = new ApolloClient({
    cache,
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          const definition = operation.query.definitions.find(
            (item) => item.kind === "OperationDefinition"
          )!;
          if (definition.kind !== "OperationDefinition")
            throw new Error("Expected operation");
          const request = {
            name: operation.operationName,
            variables: operation.variables,
            release: () => {
              observer.next({
                data: project(
                  definition.selectionSet,
                  response(operation.operationName, operation.variables)
                ),
              });
              observer.complete();
            },
          };
          requests.push(request);
          if (
            ["GetDocumentAnnotationsOnly", "GetDatacellsForExtract"].includes(
              request.name
            )
          )
            pending.push(request);
          else queueMicrotask(request.release);
        })
    ),
  });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  client.stop();
  host.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  if (originalScrollIntoView)
    Object.defineProperty(
      HTMLElement.prototype,
      "scrollIntoView",
      originalScrollIntoView
    );
  else delete (HTMLElement.prototype as any).scrollIntoView;
});

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 25));
  });
}
async function click(element: Element | null) {
  expect(element, "expected user control to exist").not.toBeNull();
  await act(async () => (element as HTMLElement).click());
  await settle();
}
function button(text: string) {
  return (
    Array.from(host.querySelectorAll("button")).find(
      (item) => item.textContent === text
    ) ?? null
  );
}
async function releaseRefreshes() {
  for (let round = 0; round < 3; round++) {
    const refreshes = pending.filter(
      (item) => item.name === "GetDocumentAnnotationsOnly"
    );
    pending = pending.filter(
      (item) => item.name !== "GetDocumentAnnotationsOnly"
    );
    await act(async () => refreshes.forEach((item) => item.release()));
    await settle();
  }
}
async function openFromGrid(index: number) {
  const row = Array.from(host.querySelectorAll("tbody tr"))[index];
  expect(row).toBeDefined();
  await click(row.querySelector('[aria-label="Cell status actions"]'));
  await click(row.querySelector('[aria-label="View Sources"]'));
  await click(button("View fixture extract"));
}
async function history(direction: "back" | "forward") {
  await act(async () => {
    window.history[direction]();
    await new Promise((resolve) =>
      window.addEventListener("popstate", resolve, { once: true })
    );
  });
  await settle();
}
function pdf() {
  return host.querySelector('[data-testid="pdf-pane"]')!;
}
function expectHighlights(index: number) {
  expect(
    host.querySelector('[aria-label="Relationships"]')?.textContent,
    "extract evidence excludes a prior document's manual relationships"
  ).toBe("");
  for (const source of sources[index]) {
    const highlight = pdf().querySelector(`[id="SELECTION_${source.id}"]`);
    expect(highlight, `${source.rawText} highlight`).not.toBeNull();
    const page = highlight!.closest(".PageAnnotationsContainer");
    expect(
      Array.from(pdf().querySelectorAll(".PageAnnotationsContainer")).indexOf(
        page!
      ),
      `${source.rawText} source page`
    ).toBe(source.page);
  }
  for (const source of sources[1 - index])
    expect(pdf().querySelector(`[id="SELECTION_${source.id}"]`)).toBeNull();
}
async function revealExtractSources(count = 2) {
  if (!host.querySelector('[data-testid="extract-pane"] [data-annotation-id]'))
    await click(button(`${count} Annotation${count === 1 ? "" : "s"}`));
}
async function inspectQuotes(index: number) {
  await revealExtractSources();
  await click(button("Default labels"));
  for (const source of sources[index]) {
    const card = host.querySelector(
      `[data-testid="extract-pane"] [data-annotation-id="${source.id}"]`
    )!;
    if (card.getAttribute("aria-current") === "true") await click(card);
    scrollTargets = [];
    await click(card);
    expect(new URLSearchParams(window.location.search).get("ann")).toBe(
      source.id
    );
    expectHighlights(index);
    expect(
      scrollTargets.some((target) => target.id === `SELECTION_${source.id}`),
      "source navigation centers its PDF quote"
    ).toBe(true);
    for (const quote of sources[index])
      expectLabel(quote, quote.id === source.id);
  }
}

it("keeps extract highlights, source focus and labels through a warm-cache A → grid → B transition and browser history", async () => {
  await act(async () =>
    root.render(
      <Provider>
        <ApolloProvider client={client}>
          <BrowserRouter>
            <CentralRouteManager />
            <Workspace />
          </BrowserRouter>
        </ApolloProvider>
      </Provider>
    )
  );
  await settle();
  await openFromGrid(0);
  // Cold A: annotation-only responses finish before the extract result.
  await releaseRefreshes();
  const extractRequest = pending.find(
    (item) => item.name === "GetDatacellsForExtract"
  );
  expect(extractRequest).toBeDefined();
  pending = pending.filter((item) => item !== extractRequest);
  await act(async () => extractRequest!.release());
  await settle();
  expectHighlights(0);
  await inspectQuotes(0);
  // A seeded Apollo with the extract's sources for BOTH documents.
  await history("back");
  await openFromGrid(1);
  expectHighlights(1);
  expect(
    requests.filter((item) => item.name === "GetDatacellsForExtract")
  ).toHaveLength(1);
  // Warm B: its correct cached evidence arrives BEFORE its own refresh response.
  await releaseRefreshes();
  expectHighlights(1);
  await inspectQuotes(1);
  await history("back");
  await history("forward");
  await releaseRefreshes();
  expectHighlights(1);
  await inspectQuotes(1);
  await history("back");
  await openFromGrid(0);
  await releaseRefreshes();
  expectHighlights(0);
  await inspectQuotes(0);
}, 15000);

it("restores manual annotations and relationships after switching extracts and valid analyses, ignoring an older refresh", async () => {
  await act(async () =>
    root.render(
      <Provider>
        <ApolloProvider client={client}>
          <BrowserRouter>
            <CentralRouteManager />
            <Workspace />
          </BrowserRouter>
        </ApolloProvider>
      </Provider>
    )
  );
  await settle();
  await openFromGrid(0);
  await releaseRefreshes();
  const extractRequest = pending.find(
    (item) => item.name === "GetDatacellsForExtract"
  )!;
  pending = pending.filter((item) => item !== extractRequest);
  await act(async () => extractRequest.release());
  await settle();
  await history("back");
  await openFromGrid(1);
  await releaseRefreshes();
  expectHighlights(1);

  await click(button("View analysis 1"));
  await settle();
  expect(
    pdf().querySelector(`[id="SELECTION_${analysisSources[0].id}"]`)
  ).not.toBeNull();
  const olderRefresh = pending.find(
    (item) =>
      item.name === "GetDocumentAnnotationsOnly" &&
      item.variables.analysisId === analyses[0].id
  );
  expect(olderRefresh).toBeDefined();
  pending = pending.filter((item) => item !== olderRefresh);
  // The source controls intentionally throttle repeated user navigation.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 110));
  });
  await click(button("View analysis 2"));
  await releaseRefreshes();
  expect(
    pdf().querySelector(`[id="SELECTION_${analysisSources[1].id}"]`)
  ).not.toBeNull();
  expect(
    pdf().querySelector(`[id="SELECTION_${analysisSources[0].id}"]`)
  ).toBeNull();
  await act(async () => olderRefresh!.release());
  await settle();
  expect(
    pdf().querySelector(`[id="SELECTION_${analysisSources[1].id}"]`)
  ).not.toBeNull();
  expect(
    pdf().querySelector(`[id="SELECTION_${analysisSources[0].id}"]`)
  ).toBeNull();

  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 110));
  });
  await click(button("View manual annotations"));
  await releaseRefreshes();
  expect(
    pdf().querySelector(`[id="SELECTION_${manual[1].id}"]`)
  ).not.toBeNull();
  expect(
    pdf().querySelector(`[id="SELECTION_${analysisSources[1].id}"]`)
  ).toBeNull();
  expect(host.querySelector('[aria-label="Relationships"]')?.textContent).toBe(
    "Document B relation"
  );
  scrollTargets = [];
  await click(button("Focus manual relationship"));
  expect(
    scrollTargets.some((target) => target.id === `SELECTION_${manual[1].id}`),
    "manual relationship focuses its PDF endpoint"
  ).toBe(true);
}, 15000);

it.each([
  ["Terms", 0, false],
  ["Terms", 0, true],
  ["FSPO", 1, false],
  ["FSPO", 1, true],
] as const)(
  "keeps %s evidence inspectable after rejection (document=%s, corrected=%s)",
  async (workflow, index, corrected) => {
    const domainData =
      workflow === "Terms"
        ? { finding: "supported", rationale: "Synthetic Terms finding" }
        : { state: "value", value: "Synthetic FSPO finding" };
    const peerColumn = {
      ...column,
      id: id("ColumnType", 2),
      name: "Shared passage heading",
    };
    const unresolvedColumn = {
      ...column,
      id: id("ColumnType", 3),
      name: "Unresolved heading",
    };
    reviewColumns = [column, peerColumn, unresolvedColumn];
    const evidence = corrected ? [sources[index][1]] : sources[index];
    reviewCells = [
      ...cells.map((cell, number) =>
        number === index
          ? {
              ...cell,
              data: { data: domainData },
              correctedData: corrected
                ? { data: { ...domainData, rationale: "Synthetic correction" } }
                : null,
              fullSourceList: evidence,
              findingEvidence: evidence.map((source) => ({
                quote: source.rawText,
                reportedPage: source.page + 1,
                locatedPage: source.page + 1,
                status: "exact",
                annotationId: source.id,
              })),
            }
          : cell
      ),
      {
        ...cells[index],
        id: id("DatacellType", 3),
        column: peerColumn,
        fullSourceList: [sources[index][0]],
      },
      {
        ...cells[index],
        id: id("DatacellType", 4),
        column: unresolvedColumn,
        fullSourceList: [],
        findingEvidence: [
          { quote: "Unlocated synthetic quote", status: "missing" },
        ],
      },
    ];
    await act(async () =>
      root.render(
        <Provider>
          <ApolloProvider client={client}>
            <BrowserRouter>
              <CentralRouteManager />
              <Workspace />
            </BrowserRouter>
          </ApolloProvider>
        </Provider>
      )
    );
    await settle();
    await openFromGrid(index);
    await releaseRefreshes();
    const extractRequest = pending.find(
      (item) => item.name === "GetDatacellsForExtract"
    )!;
    pending = pending.filter((item) => item !== extractRequest);
    await act(async () => extractRequest.release());
    await settle();
    // This review case inspects one source in the ordinary display. The separate
    // selected-only regressions retain every member of a View Sources entry.
    await click(button("Default labels"));
    await revealExtractSources(corrected ? 1 : 2);
    const selectedSource = evidence[0];
    if (selectedAnnotationIds().includes(selectedSource.id))
      await click(
        host.querySelector(
          `[data-testid="extract-pane"] [data-annotation-id="${selectedSource.id}"]`
        )
      );
    await click(
      host.querySelector(
        `[data-testid="extract-pane"] [data-annotation-id="${selectedSource.id}"]`
      )
    );
    expect(selectedAnnotationIds()).toEqual([selectedSource.id]);
    await click(button("Set zoom 150%"));
    await act(async () => new Promise((resolve) => setTimeout(resolve, 150)));
    const selection = selectedAnnotationIds();
    scrollTargets = [];
    vi.mocked(window.scrollTo).mockClear();
    await click(host.querySelector('[data-testid="extract-pane"] .reject'));
    expectHighlights(index);
    expect(selectedAnnotationIds()).toEqual(selection);
    for (const source of evidence) {
      expect(
        host.querySelector(
          `[data-testid="extract-pane"] [data-annotation-id="${source.id}"]`
        ),
        "rejected heading retains its source card"
      ).not.toBeNull();
    }
    expect(scrollTargets).toHaveLength(0);
    expect(window.scrollTo).not.toHaveBeenCalled();
    expect(host.querySelector('[aria-label="Zoom"]')?.textContent).toBe("1.5");
    expect(
      host.querySelector('[data-testid="extract-pane"]')?.textContent
    ).toContain("Rejected");
    const primaryRow = Array.from(
      host.querySelectorAll('[data-testid="extract-pane"] tbody tr')
    ).find((row) => row.textContent?.includes("Criterion"))!;
    expect(
      Array.from(
        primaryRow.nextElementSibling!.querySelectorAll("[data-annotation-id]")
      ).map((source) => source.getAttribute("data-annotation-id"))
    ).toEqual(evidence.map((source) => source.id));
    const peerRow = Array.from(
      host.querySelectorAll('[data-testid="extract-pane"] tbody tr')
    ).find((row) => row.textContent?.includes("Shared passage heading"))!;
    expect(
      (peerRow.querySelector(".reject") as HTMLButtonElement).disabled
    ).toBe(false);
    expect(peerRow.textContent).not.toContain("Rejected");
    const unresolvedRow = Array.from(
      host.querySelectorAll('[data-testid="extract-pane"] tbody tr')
    ).find((row) => row.textContent?.includes("Unresolved heading"))!;
    expect(unresolvedRow.textContent).not.toContain("Annotation");
    expect(pdf().querySelectorAll('[id^="SELECTION_"]')).toHaveLength(2);

    // Clearing evidence focus preserves native selection and saved evidence.
    await click(
      host.querySelector(
        `[data-testid="extract-pane"] [data-annotation-id="${selectedSource.id}"]`
      )
    );
    expect(selectedAnnotationIds()).toEqual([selectedSource.id]);
    expectHighlights(index);
    for (const source of sources[index]) expectLabel(source, false);
    await click(button("Show selected only"));
    expect(pdf().querySelectorAll('[id^="SELECTION_"]')).toHaveLength(1);
    await click(
      host.querySelector(
        `[data-testid="extract-pane"] [data-annotation-id="${selectedSource.id}"]`
      )
    );
    expect(
      pdf().querySelector(`[id="SELECTION_${selectedSource.id}"]`)
    ).not.toBeNull();
    await click(button("Show selected only"));
    expect(showSelectedAnnotationOnly()).toBe(true);
    await click(button("Exclude selected label"));
    expect(
      pdf().querySelector(`[id="SELECTION_${selectedSource.id}"]`)
    ).toBeNull();
    scrollTargets = [];
    vi.mocked(window.scrollTo).mockClear();
    await click(peerRow.querySelector(".reject"));
    expect(showSelectedAnnotationOnly()).toBe(true);
    expect(
      pdf().querySelector(`[id="SELECTION_${selectedSource.id}"]`)
    ).toBeNull();
    expect(scrollTargets).toHaveLength(0);
    expect(window.scrollTo).not.toHaveBeenCalled();
    await click(button("Include all labels"));
    expect(
      pdf().querySelector(`[id="SELECTION_${selectedSource.id}"]`)
    ).not.toBeNull();
    await click(button("Default labels"));
    expectHighlights(index);

    // Reload from the fixture's persisted review response with a fresh cache.
    await act(async () => root.unmount());
    client.stop();
    cache.restore({});
    client = new ApolloClient({ cache, link: client.link });
    root = createRoot(host);
    await act(async () =>
      root.render(
        <Provider>
          <ApolloProvider client={client}>
            <BrowserRouter>
              <CentralRouteManager />
              <Workspace />
            </BrowserRouter>
          </ApolloProvider>
        </Provider>
      )
    );
    await settle();
    await releaseRefreshes();
    const reloadRequest = pending.find(
      (item) => item.name === "GetDatacellsForExtract"
    );
    expect(reloadRequest).toBeDefined();
    pending = pending.filter((item) => item !== reloadRequest);
    await act(async () => reloadRequest!.release());
    for (let round = 0; round < 20; round++) {
      await settle();
      if (
        sources[index].every((source) =>
          pdf().querySelector(`[id="SELECTION_${source.id}"]`)
        )
      )
        break;
    }
    expectHighlights(index);
    expect(
      host.querySelector('[data-testid="extract-pane"]')?.textContent
    ).toContain("Rejected");
    await revealExtractSources(corrected ? 1 : 2);
    for (const source of evidence)
      expect(
        host.querySelector(
          `[data-testid="extract-pane"] [data-annotation-id="${source.id}"]`
        )
      ).not.toBeNull();
  },
  15000
);

function labelFor(source: (typeof sources)[number][number]) {
  return pdf().querySelector<HTMLElement>(
    `[data-annotation-label="${source.id}"]`
  )!;
}
function expectLabel(
  source: (typeof sources)[number][number],
  visible: boolean
) {
  const label = labelFor(source);
  expect(label, `${source.rawText} label`).not.toBeNull();
  expect(
    getComputedStyle(label).display !== "none",
    `${source.rawText} effective label visibility`
  ).toBe(visible);
}
async function mountWorkspace() {
  await act(async () =>
    root.render(
      <Provider>
        <ApolloProvider client={client}>
          <BrowserRouter>
            <CentralRouteManager />
            <Workspace />
          </BrowserRouter>
        </ApolloProvider>
      </Provider>
    )
  );
  await settle();
}
async function ordinaryEntry(index = 0, mode = "") {
  window.history.replaceState(
    null,
    "",
    `/d/reviewer/fixtures/document-${index ? "b" : "a"}?extract=${
      extract.id
    }${mode}`
  );
  await mountWorkspace();
  await releaseRefreshes();
  const request = pending.find(
    (item) => item.name === "GetDatacellsForExtract"
  );
  if (request) {
    pending = pending.filter((item) => item !== request);
    await act(async () => request.release());
    await settle();
  }
}
it("ordinary extract entry keeps workflow evidence highlights while default labels wait for hover", async () => {
  await ordinaryEntry();
  expectHighlights(0);
  for (const source of sources[0]) expectLabel(source, false);
  const first = sources[0][0];
  const target = pdf().querySelector(`[id="SELECTION_${first.id}"]`)!;
  await act(async () =>
    target.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }))
  );
  expectLabel(first, true);
  await act(async () => {
    target.dispatchEvent(
      new MouseEvent("mouseout", { bubbles: true, relatedTarget: pdf() })
    );
    await new Promise((resolve) => setTimeout(resolve, 200));
  });
  expectLabel(first, false);
  expectHighlights(0);
});

it("individual sources focus one quotation, replace its label, and toggle focus without losing viewer selection", async () => {
  await ordinaryEntry();
  await revealExtractSources();
  const cards = sources[0].map(
    (source) =>
      host.querySelector<HTMLElement>(
        `[data-testid="extract-pane"] [data-annotation-id="${source.id}"]`
      )!
  );
  await click(cards[0]);
  expectLabel(sources[0][0], true);
  expectLabel(sources[0][1], false);
  expect(cards[0].getAttribute("aria-current")).toBe("true");
  await click(cards[1]);
  expectLabel(sources[0][0], false);
  expectLabel(sources[0][1], true);
  expect(cards[0].hasAttribute("aria-current")).toBe(false);
  expect(cards[1].getAttribute("aria-current")).toBe("true");
  expectHighlights(0);
  const navigation = window.location.search;
  scrollTargets = [];
  await click(cards[1]);
  expectLabel(sources[0][1], false);
  expect(cards[1].hasAttribute("aria-current")).toBe(false);
  expect(window.location.search).toBe(navigation);
  expect(scrollTargets).toHaveLength(0);
  expectHighlights(0);
});

it.each(["", "&labels=ON_HOVER", "&labels=HIDE", "&labels=ALWAYS"])(
  "View Sources focuses its first target and preserves label mode %s",
  async (mode) => {
    window.history.replaceState(
      null,
      "",
      `${gridPath}${mode ? "?" + mode.slice(1) : ""}`
    );
    await mountWorkspace();
    await openFromGrid(0);
    await releaseRefreshes();
    const request = pending.find(
      (item) => item.name === "GetDatacellsForExtract"
    )!;
    pending = pending.filter((item) => item !== request);
    await act(async () => request.release());
    await settle();
    expect(new URLSearchParams(window.location.search).get("labels")).toBe(
      mode ? mode.slice(8) : null
    );
    expectHighlights(0);
    expectLabel(sources[0][0], mode !== "&labels=HIDE");
    expectLabel(sources[0][1], mode === "&labels=ALWAYS");
    await revealExtractSources();
    const card = host.querySelector(
      `[data-testid="extract-pane"] [data-annotation-id="${sources[0][0].id}"]`
    )!;
    expect(card.getAttribute("aria-current")).toBe("true");
    await click(
      host.querySelector(
        `[data-testid="extract-pane"] [data-annotation-id="${sources[0][1].id}"]`
      )
    );
    expect(new URLSearchParams(window.location.search).get("labels")).toBe(
      mode ? mode.slice(8) : null
    );
    expectLabel(sources[0][0], mode === "&labels=ALWAYS");
    expectLabel(sources[0][1], mode !== "&labels=HIDE");
  }
);

it("activating a source after clearing focus repeats its PDF navigation even when native selection is unchanged", async () => {
  await ordinaryEntry();
  await revealExtractSources();
  const card = host.querySelector(
    `[data-testid="extract-pane"] [data-annotation-id="${sources[0][0].id}"]`
  )!;
  await click(card);
  await act(async () => new Promise((resolve) => setTimeout(resolve, 200)));
  await click(card);
  scrollTargets = [];
  vi.mocked(window.scrollTo).mockClear();
  await click(card);
  expect(
    scrollTargets.some(
      (target) => target.id === `SELECTION_${sources[0][0].id}`
    ),
    "explicit source action navigates again to its retained PDF geometry"
  ).toBe(true);
  expectLabel(sources[0][0], true);
});

it("ordinary document navigation clears evidence focus and cannot leak a previous quotation", async () => {
  await ordinaryEntry();
  await revealExtractSources();
  await click(
    host.querySelector(
      `[data-testid="extract-pane"] [data-annotation-id="${sources[0][0].id}"]`
    )
  );
  expectLabel(sources[0][0], true);
  await click(button("Open other document"));
  await releaseRefreshes();
  expectHighlights(1);
  for (const source of sources[1]) expectLabel(source, false);
  expect(
    pdf().querySelector(`[data-annotation-label="${sources[0][0].id}"]`)
  ).toBeNull();
  expect(
    host.querySelector('[data-testid="extract-pane"] [aria-current="true"]')
  ).toBeNull();
});

it("ordinary warm SPA return to the same document after leaving the viewer starts without evidence focus", async () => {
  await ordinaryEntry();
  await revealExtractSources();
  await click(
    host.querySelector(
      `[data-testid="extract-pane"] [data-annotation-id="${sources[0][0].id}"]`
    )
  );
  expectLabel(sources[0][0], true);
  await click(button("Open extract grid"));
  expect(host.querySelector('[data-testid="pdf-pane"]')).toBeNull();
  expect(window.location.pathname).toBe(gridPath);
  await click(button("Open Document A"));
  await releaseRefreshes();
  expect(new URLSearchParams(window.location.search).get("ann")).toBeNull();
  expectHighlights(0);
  for (const source of sources[0]) expectLabel(source, false);
  await revealExtractSources();
  expect(
    host.querySelector('[data-testid="extract-pane"] [aria-current="true"]')
  ).toBeNull();
});

it.each(["ON_HOVER", "ALWAYS", "HIDE"])(
  "selected-only source inspection preserves all viewer members while toggling focus in %s",
  async (mode) => {
    const memberIds = sources[0].map((source) => source.id).join(",");
    await ordinaryEntry(0, `&ann=${memberIds}&labels=${mode}`);
    await revealExtractSources();
    await click(button("Show selected only"));
    const cards = sources[0].map(
      (source) =>
        host.querySelector<HTMLElement>(
          `[data-testid="extract-pane"] [data-annotation-id="${source.id}"]`
        )!
    );
    expectHighlights(0);
    await click(cards[0]);
    expect(cards[0].hasAttribute("aria-current")).toBe(false);
    await click(cards[0]);
    expect(cards[0].getAttribute("aria-current")).toBe("true");
    await click(cards[1]);
    expect(cards[1].getAttribute("aria-current")).toBe("true");
    expect(cards[0].hasAttribute("aria-current")).toBe(false);
    expectHighlights(0);
    const params = new URLSearchParams(window.location.search);
    expect(params.get("ann")).toBe(memberIds);
    expect(params.get("selectedOnly")).toBe("true");
    expect(params.get("labels")).toBe(mode);
    expectLabel(sources[0][0], mode === "ALWAYS");
    expectLabel(sources[0][1], mode !== "HIDE");
  }
);

it("keeps completed fields and their PDF evidence focus reviewable after the parent extract fails", async () => {
  extractError = "Another field failed; these completed findings are retained.";
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
  await act(async () =>
    root.render(
      <Provider>
        <ApolloProvider client={client}>
          <BrowserRouter>
            <CentralRouteManager />
            <Workspace />
          </BrowserRouter>
        </ApolloProvider>
      </Provider>
    )
  );
  await settle();
  expect(host.textContent).toContain("Finding 1");
  await openFromGrid(0);
  await releaseRefreshes();
  const request = pending.find(
    (item) => item.name === "GetDatacellsForExtract"
  );
  expect(request).toBeDefined();
  pending = pending.filter((item) => item !== request);
  await act(async () => request!.release());
  await settle();
  expectHighlights(0);
  await inspectQuotes(0);
  expect(requests.some((request) => request.name === "StartExtract")).toBe(
    false
  );
}, 15000);

it("retains completed findings and review controls in the full-page failed extract", async () => {
  extractError = "A field failed; completed findings were retained.";
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
  await act(async () =>
    root.render(
      <Provider>
        <ApolloProvider client={client}>
          <BrowserRouter>
            <CentralRouteManager />
            <ExtractDetail />
          </BrowserRouter>
        </ApolloProvider>
      </Provider>
    )
  );
  await settle();
  expect(host.textContent).toContain("Finding 1");
  expect(host.textContent).toContain("2 completed · 0 failed");
  expect(host.textContent).toContain("Failed");
  expect(
    host.querySelectorAll('[aria-label="Cell status actions"]')
  ).toHaveLength(2);
  expect(requests.some((request) => request.name === "StartExtract")).toBe(
    false
  );
});

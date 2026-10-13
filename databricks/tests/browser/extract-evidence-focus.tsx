import React, { useState, useCallback } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  Observable,
  useReactiveVar,
} from "@apollo/client";
import { Provider } from "jotai";
import { allStyles } from "@os-legal/ui";
import type { SelectionSetNode } from "graphql";
import { CentralRouteManager } from "../src/routing/CentralRouteManager";
import { useDocumentLoader } from "../src/components/knowledge_base/document/document_kb/useDocumentLoader";
import { useJumpToRelationship } from "../src/components/knowledge_base/document/document_kb/useJumpToRelationship";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../src/components/annotator/hooks/AnalysisHooks";
import { SingleDocumentExtractResults } from "../src/components/annotator/sidebar/SingleDocumentExtractResults";
import { DocumentVersionSelector } from "../src/components/documents/DocumentVersionSelector";
import { ViewLabelSelector } from "../src/components/annotator/labels/view_labels_selector/ViewLabelSelector";
import { ExtractDataGrid } from "../src/components/extracts/datagrid/DataGrid";
import { PDF } from "../src/components/annotator/renderers/pdf/PDF";
import { FullScreenModal } from "../src/components/knowledge_base/document/LayoutComponents";
import { CollapsibleAnnotationControls } from "../src/components/knowledge_base/document/unified_feed/CollapsibleAnnotationControls";
import { FloatingDocumentControls } from "../src/components/knowledge_base/document/FloatingDocumentControls";
import {
  useCreateAnnotation,
  useCreateUrlAnnotation,
  usePdfAnnotations,
} from "../src/components/annotator/hooks/AnnotationHooks";
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

import { useZoomManager } from "../src/components/knowledge_base/document/document_kb/useZoomManager";
import { useContainerWidth } from "../src/components/knowledge_base/document/document_kb/useContainerWidth";
const mouseFixture =
  import.meta.env.VITE_EVIDENCE_CAMPAIGN === "mouse" ||
  new URLSearchParams(window.location.search).has("mouse");
const editableFixture = new URLSearchParams(window.location.search).has(
  "editable"
);
const nativeDialogFixture = new URLSearchParams(window.location.search).has(
  "native-dialog"
);
const denseControlFixture = new URLSearchParams(window.location.search).has(
  "dense-control"
);
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
  myPermissions: editableFixture
    ? ["view_corpus", "change_corpus"]
    : ["view_corpus"],
  labelSet: null as any,
};
const documents = ["a", "b", "a-history"].map((name, index) => ({
  __typename: "DocumentType",
  id: id("DocumentType", index + 1),
  slug: `document-${name}`,
  title: `Document ${name.toUpperCase()}`,
  description: "",
  creator: owner,
  fileType: "application/pdf",
  pdfFile: `/fixture/${name}${mouseFixture ? "-mouse" : ""}.pdf`,
  pdfFileHash: name,
  pawlsParseFile: `/fixture/${name}${mouseFixture ? "-mouse" : ""}.json`,
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
documents[2].slug = "document-a";
documents[2].title = "Document A historical";
documents[2].isLatestVersion = false;
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
  error: null,
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
if (nativeDialogFixture) {
  // The ordinary annotation query requests these fields; extract projections
  // keep their existing permissions and evidence associations.
  manual[0].isEvidenceQuote = true;
  manual[0].myPermissions = ["view_annotation", "change_annotation"];
}
const denseManual = [
  [11, "Party names and addresses", 60.8, 513.6, 50.2, 101.3],
  [12, "Hire purchase agreement title", 60.8, 513.6, 50.2, 101.3],
  [41, "Section Header", 300, 560, 80, 125],
  [42, "Paragraph", 60.8, 513.6, 50.2, 101.3],
  [43, "Hire purchase agreement title", 550, 600, 110, 150],
].map(([number, text, left, right, top, bottom]) => ({
  ...annotation(documents[0], Number(number), String(text)),
  page: 0,
  myPermissions: ["view_annotation", "change_annotation", "remove_annotation"],
  json: {
    "0": {
      bounds: {
        left: Number(left),
        right: Number(right),
        top: Number(top),
        bottom: Number(bottom),
      },
      tokensJsons: [],
    },
  },
}));
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

function response(name: string, variables: Record<string, any>) {
  const index =
    name === "ResolveDocumentInCorpusFull" && variables.versionNumber === 1
      ? 2
      : documents.findIndex(
          (doc) =>
            doc.id === variables.documentId ||
            doc.slug === variables.documentSlug
        );
  const doc = documents[index];
  if (!name && variables.annotationLabelId)
    return {
      addAnnotation: {
        ok: true,
        annotation: {
          ...annotation(documents[0], 60, variables.rawText, false),
          page: variables.page,
          json: variables.json,
          annotationLabel: creationLabel,
          sourceNodeInRelationships: { edges: [] },
        },
      },
    };
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
  if (name === "GetCorpusVersions")
    return {
      document: {
        id: doc.id,
        corpusVersions: [
          {
            versionNumber: 2,
            documentId: documents[0].id,
            documentSlug: documents[0].slug,
            created: documents[0].created,
            isCurrent: true,
          },
          {
            versionNumber: 1,
            documentId: documents[2].id,
            documentSlug: documents[2].slug,
            created: documents[2].created,
            isCurrent: false,
          },
        ],
      },
    };
  if (name === "ResolveExtractById") return { extract };
  if (name === "ResolveDocumentInCorpusFull")
    return { corpusBySlugs: corpus, documentInCorpusBySlugs: doc };
  if (name === "GetDocumentKnowledgeAndAnnotations")
    return {
      document: {
        ...doc,
        allAnnotations:
          denseControlFixture && index === 0 ? denseManual : [manual[index]],
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
            : denseControlFixture && index === 0
            ? denseManual
            : [manual[index]],
        allRelationships: variables.analysisId ? [] : [relationships[index]],
      },
    };
  }
  throw new Error(`Unexpected network operation ${name}`);
}

function DocumentView({ documentId }: { documentId: string }) {
  const location = useLocation();
  const [paneOpen, setPaneOpen] = useState(true);
  const [paneWide, setPaneWide] = useState(false);
  const { containerWidth, containerRefCallback } = useContainerWidth();
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
  const createAnnotation = useCreateAnnotation();
  const createUrlAnnotation = useCreateUrlAnnotation();
  const { pdfAnnotations } = usePdfAnnotations();
  const { zoomLevel, setZoomLevel } = useZoomLevel();
  const { setSpanLabelsToView, setActiveSpanLabel } = useAnnotationControls();
  const getPanelWidthPercentage = useCallback(
    () => (paneWide ? 48 : 32),
    [paneWide]
  );
  useZoomManager({
    zoomLevel,
    setZoomLevel,
    activeLayer:
      lifecycleFixture || import.meta.env.VITE_EVIDENCE_CAMPAIGN === "input"
        ? "document"
        : "knowledge",
    showRightPanel: paneOpen,
    isMobile: false,
    mode: "extract",
    customWidth: paneWide ? 48 : 32,
    getPanelWidthPercentage,
  });
  useJumpToRelationship();
  const content = (
    <>
      <h1>{loader.combinedData?.document?.title}</h1>
      {import.meta.env.VITE_EVIDENCE_CAMPAIGN === "input" && (
        <>
          <CollapsibleAnnotationControls showLabelFilters />
          <FloatingDocumentControls
            bareContainer={!paneOpen}
            showRightPanel={paneOpen}
            extractsOpen={paneOpen}
            onExtractsClick={() => setPaneOpen((open) => !open)}
            readOnly={!editableFixture}
          />
        </>
      )}
      {lifecycleFixture && (
        <>
          <DocumentVersionSelector
            documentId={documentId}
            corpusId={corpus.id}
          />
          <section
            aria-label="Native label filter"
            style={{ width: 300, display: "inline-block" }}
          >
            <ViewLabelSelector />
          </section>
        </>
      )}
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
      {denseControlFixture && (
        <button onClick={() => setZoomLevel(1.27)}>Set zoom 127%</button>
      )}
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
      {mouseFixture && (
        <>
          <button
            onClick={() =>
              setSpanLabelsToView([
                sources[0][0].annotationLabel,
                sources[0][2].annotationLabel,
              ] as any)
            }
          >
            Show only A and C labels
          </button>
          <button onClick={() => setActiveSpanLabel(creationLabel as any)}>
            Choose manual label
          </button>
        </>
      )}
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
      <button onClick={() => setPaneOpen((value) => !value)}>
        Toggle Extract pane
      </button>
      <button onClick={() => setPaneWide((value) => !value)}>
        Resize Extract pane
      </button>
      <div style={{ display: "flex", height: 760 }}>
        <section
          data-testid="pdf-pane"
          ref={containerRefCallback}
          style={{ overflow: "auto", flex: 1, minWidth: 0 }}
        >
          <PDF
            read_only={!editableFixture}
            containerWidth={containerWidth}
            createAnnotationHandler={createAnnotation}
            createUrlAnnotationHandler={createUrlAnnotation}
          />
        </section>
        {paneOpen && (
          <section
            data-testid="extract-pane"
            style={{ width: paneWide ? "48%" : "32%", overflow: "auto" }}
          >
            <SingleDocumentExtractResults
              columns={columns}
              datacells={dataCells}
            />
          </section>
        )}
      </div>
      <section aria-label="Relationships">
        {pdfAnnotations.relations.map((relation) => (
          <span key={relation.id}>{relation.label.text}</span>
        ))}
      </section>
    </>
  );
  return mouseFixture ? (
    <FullScreenModal
      id="knowledge-base-modal"
      open={true}
      onClose={() => navigate(gridPath)}
    >
      <div>{content}</div>
    </FullScreenModal>
  ) : (
    content
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

// The same native composition as document-extract-transition, with immediate synthetic
// GraphQL delivery and only PDF byte decoding substituted by the runner's Vite aliases.
const reviewCells = [...cells];
const reviewColumns = [column];
const rejectedCellIds = new Set<string>();
// Two distinct workflow quotes on nearby non-overlapping passages put their label
// bars in conflict while keeping each native highlight separately pointer reachable.
sources[0][0].json = {
  "1": {
    bounds: { left: 50, right: 200, top: 200, bottom: 220 },
    tokensJsons: [],
  },
};
sources[0][1].page = 1;
sources[0][1].json = {
  "1": {
    bounds: { left: 50, right: 200, top: 180, bottom: 190 },
    tokensJsons: [],
  },
};
if (mouseFixture) {
  // Distinct workflow annotations at the same location, a partial overlap and
  // an evidence span connected only through that partial overlap.
  sources[0] = [
    annotation(documents[0], 11, "Evidence A"),
    annotation(documents[0], 12, "Evidence B"),
    annotation(documents[0], 41, "Evidence C"),
    annotation(documents[0], 42, "Evidence D"),
    annotation(documents[0], 43, "Evidence E"),
  ];
  sources[0].forEach((source, index) => {
    source.page = 1;
    const [left, right] =
      index === 2 ? [150, 300] : index === 4 ? [280, 420] : [50, 200];
    source.json = {
      "1": { bounds: { left, right, top: 200, bottom: 220 }, tokensJsons: [] },
    };
  });
  cells[0].fullSourceList = sources[0];
  // Reusing A in a second finding does not create a second viewer identity.
  reviewColumns.push({
    ...column,
    id: id("ColumnType", 2),
    name: "Shared criterion",
  });
  reviewCells.push({
    ...cells[0],
    id: id("DatacellType", 4),
    column: reviewColumns[1],
    data: { data: "Shared finding" },
    fullSourceList: [sources[0][0]],
  });
}
if (denseControlFixture) {
  // Both external queries describe the same quotes. Only the ordinary document
  // response supplies edit permissions requested by the native loader.
  sources[0] = denseManual.map((source) => ({
    ...source,
    myPermissions: ["READ"],
  }));
  cells[0].fullSourceList = sources[0];
  reviewCells[3].fullSourceList = [sources[0][0]];
}
const creationLabel = {
  __typename: "AnnotationLabelType",
  id: id("AnnotationLabelType", 60),
  text: "Created manual",
  color: "#08916b",
  labelType: "TOKEN_LABEL",
  icon: null,
  description: "",
};
if (editableFixture)
  corpus.labelSet = {
    __typename: "LabelSetType",
    id: id("LabelSetType", 1),
    title: "Fixture labels",
    description: "",
    allAnnotationLabels: [creationLabel],
  };
cache.restore({});
authStatusVar("AUTHENTICATED");
authInitCompleteVar(true);
showAnnotationLabels(LabelDisplayBehavior.ON_HOVER);
showSelectedAnnotationOnly(false);
showStructuralAnnotations(false);
selectedAnnotationIds([]);
selectedExtractIds([]);
selectedAnalysesIds([]);
openedDocument(null);
openedCorpus(null);
openedExtract(null);
selectedExtract(null);
onlyDisplayTheseAnnotations([]);
displayAnnotationOnAnnotatorLoad(null);
routeLoading(false);
routeError(null);
navigationCircuitBreaker.reset();
const requestedEntry = new URLSearchParams(window.location.search);
// Fixture configuration survives native URL canonicalization and reload. The
// server supplies it independently of document inspection query parameters.
const lifecycleFixture =
  import.meta.env.VITE_EVIDENCE_CAMPAIGN === "lifecycle" ||
  requestedEntry.has("lifecycle");
if (lifecycleFixture) {
  const peer = annotation(documents[0], 50, "Document A peer quote");
  peer.page = 1;
  peer.json = {
    "1": {
      bounds: { left: 260, right: 400, top: 240, bottom: 260 },
      tokensJsons: [],
    },
  };
  sources[0].push(peer);
  sources[0][0].page = 0;
  sources[0][0].json = {
    "0": {
      bounds: { left: 50, right: 200, top: 200, bottom: 220 },
      tokensJsons: [],
    },
    "1": {
      bounds: { left: 50, right: 200, top: 200, bottom: 220 },
      tokensJsons: [],
    },
  };
}
window.history.replaceState(
  null,
  "",
  `/d/reviewer/fixtures/document-a?extract=${extract.id}${
    requestedEntry.get("ann")
      ? `&ann=${requestedEntry.get("ann")}`
      : requestedEntry.get("target")
      ? `&ann=${sources[0][0].id},${sources[0][1].id}`
      : ""
  }${
    requestedEntry.get("labels")
      ? `&labels=${requestedEntry.get("labels")}`
      : ""
  }${requestedEntry.get("v") ? `&v=${requestedEntry.get("v")}` : ""}${
    lifecycleFixture ? "&lifecycle=1" : ""
  }`
);
const client = new ApolloClient({
  cache,
  link: new ApolloLink(
    (operation) =>
      new Observable((observer) => {
        const definition = operation.query.definitions.find(
          (item) => item.kind === "OperationDefinition"
        )!;
        if (definition.kind !== "OperationDefinition")
          throw new Error("Expected operation");
        queueMicrotask(() => {
          observer.next({
            data: project(
              definition.selectionSet,
              response(operation.operationName, operation.variables)
            ),
          });
          observer.complete();
        });
      })
  ),
});
if (mouseFixture) {
  // Match the native entrypoint's component styles for fullscreen/child dialogs.
  const style = document.createElement("style");
  style.id = "opencontracts-ui-styles";
  style.textContent = allStyles;
  document.head.appendChild(style);
}
createRoot(document.getElementById("root")!).render(
  <Provider>
    <ApolloProvider client={client}>
      <BrowserRouter>
        <CentralRouteManager />
        <Workspace />
      </BrowserRouter>
    </ApolloProvider>
  </Provider>
);

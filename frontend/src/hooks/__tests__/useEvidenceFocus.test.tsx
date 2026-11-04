import React, { useEffect, useRef } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { selectedDocVersion } from "../../graphql/cache";
import { selectedDocumentAtom } from "../../components/annotator/context/DocumentAtom";
import { pdfAnnotationsAtom } from "../../components/annotator/context/AnnotationAtoms";
import {
  PdfAnnotations,
  ServerTokenAnnotation,
} from "../../components/annotator/types/annotations";
import {
  AnnotationLabelType,
  DocumentType,
  LabelType,
} from "../../types/graphql-api";
import {
  useEvidenceFocus,
  useEvidenceFocusEscape,
  useEvidenceFocusNavigation,
} from "../useEvidenceFocus";

function annotation(id: string, eligible = true) {
  return new ServerTokenAnnotation(
    0,
    {
      id: `label-${id}`,
      text: "Synthetic criterion",
      color: "#616a6b",
      labelType: LabelType.TokenLabel,
      readonly: true,
    } as AnnotationLabelType,
    "Synthetic retained quotation",
    false,
    {
      0: {
        bounds: { left: 10, right: 40, top: 20, bottom: 30 },
        tokensJsons: [],
        rawText: "Synthetic retained quotation",
      },
    },
    [],
    false,
    false,
    false,
    id,
    undefined,
    null,
    eligible
  );
}

const sourceA = annotation("source-a");
const sourceB = annotation("source-b");

function Surface({
  zoom,
  requested,
}: {
  zoom: number;
  requested: (id: string) => void;
}) {
  const viewer = useRef<HTMLDivElement>(null);
  useEvidenceFocusNavigation();
  useEvidenceFocusEscape(viewer);
  const { focusedEvidenceId, evidenceNavigation, navigateToEvidence } =
    useEvidenceFocus();
  const navigate = useNavigate();
  useEffect(() => {
    if (evidenceNavigation) requested(evidenceNavigation.annotationId);
  }, [evidenceNavigation, requested]);
  return (
    <>
      <output aria-label="Inspection">{focusedEvidenceId ?? "None"}</output>
      <div
        ref={viewer}
        role="region"
        aria-label="PDF viewer"
        data-zoom={zoom}
      />
      <button onClick={() => navigateToEvidence("source-b")}>Inspect B</button>
      <button
        onClick={() => navigate("/document?ann=source-a&findingCell=cell-a")}
      >
        Effective version
      </button>
      <button
        onClick={() =>
          navigate("/document?ann=source-b&findingCell=other-cell")
        }
      >
        Other finding
      </button>
    </>
  );
}

function entry(
  initial: ServerTokenAnnotation[] = [sourceA, sourceB],
  route = "/document?ann=source-a&findingCell=cell-a&findingVersion=original"
) {
  const store = createStore();
  store.set(selectedDocumentAtom, {
    id: "document-a",
    pdfFileHash: "synthetic-hash",
  } as DocumentType);
  store.set(pdfAnnotationsAtom, new PdfAnnotations(initial, [], []));
  const requests: string[] = [];
  const requested = (id: string) => requests.push(id);
  const view = (zoom: number) => (
    <Provider store={store}>
      <MemoryRouter initialEntries={[route]}>
        <Surface zoom={zoom} requested={requested} />
      </MemoryRouter>
    </Provider>
  );
  const rendered = render(view(1));
  return {
    requests,
    annotations(values: ServerTokenAnnotation[]) {
      act(() =>
        store.set(pdfAnnotationsAtom, new PdfAnnotations(values, [], []))
      );
    },
    zoom(value: number) {
      rendered.rerender(view(value));
    },
  };
}

beforeEach(() => {
  selectedDocVersion(null);
});
afterEach(cleanup);

describe("explicit evidence entry lifecycle", () => {
  it("restores the entry once when extract loading removes then restores its eligible source", () => {
    const page = entry();
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-a");
    page.annotations([]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    page.annotations([sourceA, sourceB]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-a");
    expect(page.requests).toEqual(["source-a", "source-a"]);
    page.annotations([sourceA, sourceB]);
    page.zoom(2);
    expect(page.requests).toEqual(["source-a", "source-a"]);
  });

  it("sends a PDF-centering intent after a delayed source becomes eligible", () => {
    const page = entry([]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    expect(page.requests).toEqual([]);
    page.annotations([sourceA]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-a");
    expect(page.requests).toEqual(["source-a"]);
  });

  it.each(["original", "effective"])(
    "does not replay a handled %s entry during stable annotation renders or zoom",
    (version) => {
      const page = entry(
        [sourceA, sourceB],
        `/document?ann=source-a&findingCell=cell-a&findingVersion=${version}`
      );
      const initialRequests = [...page.requests];
      expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-a");
      page.annotations([sourceA, sourceB]);
      page.zoom(0.5);
      page.zoom(2);
      expect(page.requests).toEqual(initialRequests);
      expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-a");
    }
  );

  it("preserves explicit Escape through stable source renders and zoom", () => {
    const page = entry();
    const initialRequests = [...page.requests];
    fireEvent.keyDown(screen.getByRole("region", { name: "PDF viewer" }), {
      key: "Escape",
    });
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    page.annotations([sourceA, sourceB]);
    page.zoom(2);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    expect(page.requests).toEqual(initialRequests);
  });

  it("does not replace another explicit inspection with the old URL entry", () => {
    const page = entry();
    const initialCount = page.requests.length;
    fireEvent.click(screen.getByRole("button", { name: "Inspect B" }));
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-b");
    page.annotations([sourceA, sourceB]);
    page.zoom(2);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-b");
    expect(page.requests).toHaveLength(initialCount + 1);
    expect(page.requests.at(-1)).toBe("source-b");
  });

  it("does not reapply a dismissed entry after sources are refreshed", () => {
    const page = entry();
    const initialRequests = [...page.requests];
    fireEvent.keyDown(screen.getByRole("region", { name: "PDF viewer" }), {
      key: "Escape",
    });
    page.annotations([]);
    page.annotations([sourceA, sourceB]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    expect(page.requests).toEqual(initialRequests);
  });

  it("does not reapply the old entry after another inspection and source refresh", () => {
    const page = entry();
    fireEvent.click(screen.getByRole("button", { name: "Inspect B" }));
    const explicitRequests = [...page.requests];
    page.annotations([]);
    page.annotations([sourceA, sourceB]);
    expect(screen.getByLabelText("Inspection")).not.toHaveTextContent(
      "source-a"
    );
    expect(page.requests).toEqual(explicitRequests);
  });

  it("keeps Escape authoritative when the entry already auto-cleared during an empty projection", () => {
    const page = entry();
    page.annotations([]);
    const requestsBeforeEscape = [...page.requests];
    fireEvent.keyDown(screen.getByRole("region", { name: "PDF viewer" }), {
      key: "Escape",
    });
    page.annotations([sourceA, sourceB]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    expect(page.requests).toEqual(requestsBeforeEscape);
    // A later explicit version entry has its own intent and is still allowed.
    fireEvent.click(screen.getByRole("button", { name: "Effective version" }));
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-a");
    expect(page.requests).toEqual([...requestsBeforeEscape, "source-a"]);
  });

  it("keeps a manual inspection authoritative when replacement empties in the same update", () => {
    const page = entry();
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Inspect B" }));
      page.annotations([]);
    });
    const explicitRequests = [...page.requests];
    page.annotations([sourceA, sourceB]);
    expect(screen.getByLabelText("Inspection")).not.toHaveTextContent(
      "source-a"
    );
    expect(page.requests).toEqual(explicitRequests);
  });

  it("allows dismissal while the initial entry is still waiting for its source", () => {
    const page = entry([]);
    fireEvent.keyDown(screen.getByRole("region", { name: "PDF viewer" }), {
      key: "Escape",
    });
    page.annotations([sourceA]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    expect(page.requests).toEqual([]);
  });

  it("treats an explicit version change as a new entry context", () => {
    const page = entry();
    const initialCount = page.requests.length;
    fireEvent.click(screen.getByRole("button", { name: "Effective version" }));
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-a");
    expect(page.requests).toHaveLength(initialCount + 1);
    expect(page.requests.at(-1)).toBe("source-a");
  });

  it("does not inherit a source into another finding while its target is missing", () => {
    const page = entry([sourceA]);
    const initialRequests = [...page.requests];
    fireEvent.click(screen.getByRole("button", { name: "Other finding" }));
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    expect(page.requests).toEqual(initialRequests);
    page.annotations([sourceB]);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("source-b");
    expect(page.requests).toEqual([...initialRequests, "source-b"]);
  });

  it("refuses a missing or unlocated legacy source until evidence is eligible", () => {
    // An ambiguous quotation supplies no selected source; retained legacy
    // annotations cannot become entries solely because their old ID exists.
    const page = entry([], "/document?ann=unlocated-source");
    page.annotations([annotation("unlocated-source", false)]);
    page.zoom(2);
    expect(screen.getByLabelText("Inspection")).toHaveTextContent("None");
    expect(page.requests).toEqual([]);
  });
});

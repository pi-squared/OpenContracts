import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentNode } from "graphql";
import { CentralRouteManager } from "../src/routing/CentralRouteManager";
import {
  RESOLVE_DOCUMENT_BY_SLUGS_FULL,
  RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
} from "../src/graphql/queries";
import {
  authStatusVar,
  authInitCompleteVar,
  openedDocument,
  openedCorpus,
  openedExtract,
  routeLoading,
  routeError,
} from "../src/graphql/cache";
import { navigationCircuitBreaker } from "../src/utils/navigationCircuitBreaker";

const boundary = vi.hoisted(() => ({ resolve: vi.fn() }));
vi.mock("@apollo/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@apollo/client")>()),
  useApolloClient: () => ({}),
  useLazyQuery: (query: DocumentNode) => [
    (options: unknown) => boundary.resolve(query, options),
    {},
  ],
}));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let host: HTMLDivElement;
let root: Root;
const sourcePath = "/d/reviewer/agreements/source-agreement";
const authorityPath = "/d/reviewer/section-52";
const sourceDocument = {
  id: "document-52",
  slug: "source-agreement",
  title: "Source agreement",
  description: "",
  fileType: "application/pdf",
  isPublic: false,
  pdfFile: "/media/source.pdf",
  backendLock: false,
  isLatestVersion: true,
  creator: { id: "user-1", slug: "reviewer", username: "reviewer" },
};
const authorityDocument = {
  ...sourceDocument,
  id: "document-124",
  slug: "section-52",
  title: "Consumer Credit Act 1995 — Section 52",
  fileType: "text/plain",
  pdfFile: null,
};
const sourceCorpus = {
  id: "corpus-6",
  slug: "agreements",
  title: "Agreements",
  description: "",
  isPublic: false,
  creator: sourceDocument.creator,
  labelSet: null,
  documentCount: 1,
  annotationCount: 0,
};

function Navigation({ target = authorityPath }: { target?: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate(target)}>Open authority</button>
      <span data-testid="route">{location.pathname}</span>
    </>
  );
}

beforeEach(() => {
  openedDocument(null);
  openedCorpus(null);
  openedExtract(null);
  routeLoading(false);
  routeError(null);
  authStatusVar("AUTHENTICATED");
  authInitCompleteVar(true);
  navigationCircuitBreaker.reset();
  boundary.resolve.mockReset();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
});

describe("reference target route resolution", () => {
  it("keeps the requested authority URL while the old agreement and corpus are still selected", async () => {
    let release:
      | ((value: {
          data: { documentBySlugs: typeof authorityDocument };
        }) => void)
      | undefined;
    boundary.resolve.mockImplementation((query, options) => {
      if (query === RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL) {
        return Promise.resolve({
          data: {
            documentInCorpusBySlugs: sourceDocument,
            corpusBySlugs: sourceCorpus,
          },
        });
      }
      if (
        query === RESOLVE_DOCUMENT_BY_SLUGS_FULL &&
        options.variables.documentSlug === "section-52"
      ) {
        return new Promise((resolve) => {
          release = resolve;
        });
      }
      throw new Error("Unexpected route resolution");
    });
    await act(async () =>
      root.render(
        <MemoryRouter initialEntries={[sourcePath]}>
          <CentralRouteManager />
          <Navigation />
        </MemoryRouter>
      )
    );
    expect(openedDocument()?.id).toBe("document-52");
    expect(openedCorpus()?.id).toBe("corpus-6");
    await act(async () =>
      host.querySelector<HTMLButtonElement>("button")!.click()
    );
    expect(host.querySelector('[data-testid="route"]')?.textContent).toBe(
      authorityPath
    );
    expect(openedDocument()?.id).toBe("document-52");
    expect(release).toBeDefined();
    await act(async () =>
      release!({ data: { documentBySlugs: authorityDocument } })
    );
    expect(host.querySelector('[data-testid="route"]')?.textContent).toBe(
      authorityPath
    );
    expect(openedDocument()?.id).toBe("document-124");
    expect(openedDocument()?.fileType).toBe("text/plain");
    expect(openedCorpus()).toBeNull();
  });

  it("keeps standalone authority routes outside a stale corpus while resolving", async () => {
    // Pause auth so Phase1 cannot clear stale state. This isolates the actual
    // Phase3 canonical redirect behavior, using native reactive vars/router.
    authStatusVar("LOADING");
    // Seed through the real Phase1 path rather than constructing a fake router.
    boundary.resolve.mockImplementation(() =>
      Promise.resolve({
        data: {
          documentInCorpusBySlugs: sourceDocument,
          corpusBySlugs: sourceCorpus,
        },
      })
    );
    authStatusVar("AUTHENTICATED");
    await act(async () =>
      root.render(
        <MemoryRouter initialEntries={[sourcePath]}>
          <CentralRouteManager />
          <Navigation />
        </MemoryRouter>
      )
    );
    await act(async () => {
      authStatusVar("LOADING");
    });
    await act(async () =>
      host.querySelector<HTMLButtonElement>("button")!.click()
    );
    expect(host.querySelector('[data-testid="route"]')?.textContent).toBe(
      authorityPath
    );
  });

  it("does not put a standalone URL back inside the previously selected corpus", async () => {
    const standalone = "/d/reviewer/source-agreement";
    boundary.resolve.mockImplementation(() =>
      Promise.resolve({
        data: {
          documentInCorpusBySlugs: sourceDocument,
          corpusBySlugs: sourceCorpus,
        },
      })
    );
    await act(async () =>
      root.render(
        <MemoryRouter initialEntries={[sourcePath]}>
          <CentralRouteManager />
          <Navigation target={standalone} />
        </MemoryRouter>
      )
    );
    await act(async () => {
      authStatusVar("LOADING");
    });
    await act(async () =>
      host.querySelector<HTMLButtonElement>("button")!.click()
    );
    expect(host.querySelector('[data-testid="route"]')?.textContent).toBe(
      standalone
    );
  });

  it("waits for the requested corpus when the document slug is already selected", async () => {
    const target = "/d/reviewer/statute/source-agreement";
    boundary.resolve.mockImplementation(() =>
      Promise.resolve({
        data: {
          documentInCorpusBySlugs: sourceDocument,
          corpusBySlugs: sourceCorpus,
        },
      })
    );
    await act(async () =>
      root.render(
        <MemoryRouter initialEntries={[sourcePath]}>
          <CentralRouteManager />
          <Navigation target={target} />
        </MemoryRouter>
      )
    );
    await act(async () => {
      authStatusVar("LOADING");
    });
    await act(async () =>
      host.querySelector<HTMLButtonElement>("button")!.click()
    );
    expect(host.querySelector('[data-testid="route"]')?.textContent).toBe(
      target
    );
  });
});

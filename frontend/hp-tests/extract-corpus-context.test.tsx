import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  InMemoryCache,
  Observable,
} from "@apollo/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { DesktopDocumentLayout } from "../src/components/knowledge_base/document/layouts/DesktopDocumentLayout";

// Keep the real toolbar and extracts gate; unrelated viewer surfaces do not
// participate in resolving membership. Network responses model DocumentPath.
vi.mock("../src/components/knowledge_base/document/StyledContainers", () => ({
  ContentArea: ({ children }: any) => <>{children}</>,
  MainContentArea: ({ children }: any) => <>{children}</>,
  SlidingPanel: ({ children }: any) => <>{children}</>,
  ResizeHandle: ({ children }: any) => <>{children}</>,
}));
vi.mock("../src/components/knowledge_base/document/LayoutComponents", () => ({
  DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS: "child-modal",
  FullScreenModal: ({ children }: any) => <>{children}</>,
}));
vi.mock("../src/components/knowledge_base/markdown/SafeMarkdown", () => ({
  SafeMarkdown: ({ children }: any) => <>{children}</>,
}));
vi.mock("../src/components/annotator/labels/EnhancedLabelSelector", () => ({
  EnhancedLabelSelector: ({ children }: any) => <>{children}</>,
}));
vi.mock(
  "../src/components/knowledge_base/document/floating_summary_preview/FloatingSummaryPreview",
  () => ({ FloatingSummaryPreview: ({ children }: any) => <>{children}</> })
);
vi.mock("../src/components/knowledge_base/document/ZoomControls", () => ({
  ZoomControls: ({ children }: any) => <>{children}</>,
}));
vi.mock(
  "../src/components/knowledge_base/document/FloatingDocumentInput",
  () => ({ FloatingDocumentInput: ({ children }: any) => <>{children}</> })
);
vi.mock(
  "../src/components/knowledge_base/document/FloatingAnalysesPanel",
  () => ({ FloatingAnalysesPanel: ({ children }: any) => <>{children}</> })
);
vi.mock(
  "../src/components/knowledge_base/document/FloatingExtractsPanel",
  () => ({ FloatingExtractsPanel: ({ children }: any) => <>{children}</> })
);
vi.mock(
  "../src/components/knowledge_base/document/document_kb/RightPanelContent",
  () => ({ RightPanelContent: ({ children }: any) => <>{children}</> })
);
vi.mock(
  "../src/components/knowledge_base/document/document_kb/DocumentModals",
  () => ({
    DocumentModals: (p: any) =>
      p.showAddToCorpusModal ? <div>Add to Corpus</div> : null,
  })
);
vi.mock(
  "../src/components/knowledge_base/document/document_kb/ContextBar",
  () => ({ AnalysisExtractContextBar: ({ children }: any) => <>{children}</> })
);
vi.mock(
  "../src/components/knowledge_base/document/document_kb/SidebarTabs",
  () => ({ DesktopSidebarTabs: ({ children }: any) => <>{children}</> })
);
vi.mock(
  "../src/components/knowledge_base/document/document_kb/HeaderBar",
  () => ({ HeaderBar: ({ children }: any) => <>{children}</> })
);

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const corpus = {
  id: "c1",
  slug: "existing",
  title: "Existing corpus",
  creator: { slug: "owner" },
};
let host: HTMLDivElement, root: Root, client: ApolloClient<any>;
let requests: { name: string; variables: any }[];
let pages: any[][];
let fail = false;
let release: (() => void) | undefined;
let delay = false;
function Location() {
  const location = useLocation();
  return (
    <output>
      {location.pathname} {location.state?.openDocumentExtracts}
    </output>
  );
}
function Layout({
  documentId = "d1",
  corpusId,
}: {
  documentId?: string;
  corpusId?: string;
}) {
  const [add, setAdd] = React.useState(false);
  const [extracts, setExtracts] = React.useState(false);
  return (
    <>
      <DesktopDocumentLayout
        {...({
          documentId,
          corpusId,
          activeLayer: "document",
          showRightPanel: false,
          showAddToCorpusModal: add,
          setShowAddToCorpusModal: setAdd,
          showExtractsPanel: extracts,
          setShowExtractsPanel: setExtracts,
          analyses: [],
          extracts: [],
          notes: [],
          metadata: {},
          floatingControlsState: { offset: 0, visible: true },
          handleClose: () => {},
          pdfAnnotations: {},
        } as any)}
      />
      <Location />
      {extracts && <div>Extracts open</div>}
    </>
  );
}
async function render(documentId = "d1", corpusId?: string) {
  await act(async () =>
    root.render(
      <ApolloProvider client={client}>
        <MemoryRouter initialEntries={["/d/owner/sample"]}>
          <Layout documentId={documentId} corpusId={corpusId} />
        </MemoryRouter>
      </ApolloProvider>
    )
  );
}
async function click(text: string) {
  const element = [...document.querySelectorAll("button")].find(
    (el) =>
      el.textContent?.includes(text) ||
      el.getAttribute("aria-label") === text ||
      el.getAttribute("title") === text
  );
  expect(element, text).toBeTruthy();
  await act(async () => element!.click());
}
beforeEach(() => {
  pages = [[{ isCurrent: true, isDeleted: false, corpus }]];
  requests = [];
  fail = false;
  delay = false;
  release = undefined;
  client = new ApolloClient({
    cache: new InMemoryCache(),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          requests.push({
            name: operation.operationName,
            variables: operation.variables,
          });
          const respond = () => {
            if (fail) {
              observer.error(new Error("Offline"));
              return;
            }
            const index = operation.variables.after
              ? Number(operation.variables.after)
              : 0;
            observer.next({
              data: {
                document: {
                  id: operation.variables.documentId,
                  slug: "sample",
                  creator: { slug: "owner" },
                  pathRecords: {
                    edges: pages[index].map((node) => ({ node })),
                    pageInfo: {
                      hasNextPage: index < pages.length - 1,
                      endCursor: String(index + 1),
                    },
                  },
                },
              },
            });
            observer.complete();
          };
          if (delay) release = respond;
          else respond();
        })
    ),
  });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  client.stop();
});
it("uses an existing membership from the library instead of asking to add again", async () => {
  await render();
  await click("View extracts");
  expect(document.body.textContent).not.toContain("Add to Corpus");
  expect(host.textContent).toContain("/d/owner/existing/sample d1");
  expect(requests.map((r) => r.name)).toEqual(["GetDocumentExtractCorpora"]);
});
it("retains Add to Corpus only for a confirmed unassigned document", async () => {
  pages = [[]];
  await render();
  await click("View extracts");
  expect(host.textContent).toContain("Add to Corpus");
});
it("reads all pages, deduplicates corpora and offers existing contexts", async () => {
  pages.push([
    { isCurrent: true, isDeleted: false, corpus },
    {
      isCurrent: true,
      isDeleted: false,
      corpus: { ...corpus, id: "c2", slug: "second", title: "Second corpus" },
    },
  ]);
  await render();
  await click("View extracts");
  expect(document.body.textContent).toContain("Choose a corpus for extracts");
  expect(document.body.textContent).not.toContain("Add to Corpus");
  expect(
    [...document.querySelectorAll("button")].filter(
      (el) => el.textContent === "Existing corpus"
    )
  ).toHaveLength(1);
  await click("Second corpus");
  expect(host.textContent).toContain("/d/owner/second/sample d1");
  expect(requests[1].variables.after).toBe("1");
});
it("does not turn a lookup failure into missing membership and can retry", async () => {
  fail = true;
  await render();
  await click("View extracts");
  expect(document.body.textContent).toContain(
    "Unable to load corpus memberships"
  );
  expect(document.body.textContent).not.toContain("Add to Corpus");
  fail = false;
  await click("Retry");
  expect(host.textContent).toContain("/d/owner/existing/sample d1");
});
it("discards a pending lookup after switching documents", async () => {
  delay = true;
  await render();
  await click("View extracts");
  await render("d2");
  await act(async () => release!());
  expect(host.textContent).not.toContain("/existing/");
  expect(document.body.textContent).not.toContain(
    "Choose a corpus for extracts"
  );
});
it("keeps corpus entry local without membership requests or writes", async () => {
  await render("d1", "c1");
  await click("View extracts");
  expect(host.textContent).toContain("Extracts open");
  expect(requests).toEqual([]);
});

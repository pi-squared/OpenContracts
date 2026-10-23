import React, { act } from "react";
import { createRoot } from "react-dom/client";
import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  Observable,
} from "@apollo/client";
import { expect, it, vi } from "vitest";
import { cache } from "../src/graphql/cache";
import { GET_DOCUMENTS_FOR_LIST } from "../src/graphql/queries";
import { useUploadMutations } from "../src/components/widgets/modals/UploadModal/hooks/useUploadMutations";
import { importDocumentMultipart } from "../src/utils/importHttp";

vi.mock("../src/utils/importHttp", () => ({
  importDocumentMultipart: vi.fn(),
  importDocumentsZipMultipart: vi.fn(),
}));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

it("finds an uploaded title after an earlier empty search was cached", async () => {
  cache.restore({});
  let uploaded = false;
  const title = "Public sample title 42";
  const uploadedDocument = {
    __typename: "DocumentType",
    id: "new-document",
    slug: "sample-42",
    title,
    fileType: "application/pdf",
    backendLock: false,
    pageCount: 2,
    icon: "",
    created: "2026-10-12T00:00:00Z",
    creator: { __typename: "UserType", id: "owner", slug: "owner", email: "" },
  };
  const client = new ApolloClient({
    cache,
    link: new ApolloLink(
      () =>
        new Observable((observer) => {
          observer.next({
            data: {
              documents: {
                __typename: "DocumentTypeConnection",
                edges: uploaded
                  ? [
                      {
                        __typename: "DocumentTypeEdge",
                        cursor: "new",
                        node: uploadedDocument,
                      },
                    ]
                  : [],
                pageInfo: {
                  __typename: "PageInfo",
                  hasNextPage: false,
                  hasPreviousPage: false,
                  startCursor: uploaded ? "new" : null,
                  endCursor: uploaded ? "new" : null,
                },
              },
            },
          });
          observer.complete();
        })
    ),
  });
  const query = {
    query: GET_DOCUMENTS_FOR_LIST,
    variables: { textSearch: title, limit: 20 },
  };
  expect((await client.query(query)).data.documents.edges).toEqual([]);
  vi.mocked(importDocumentMultipart).mockImplementation(async () => {
    uploaded = true;
    return { ok: true, document_id: 42, status: "created" };
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  let upload: ReturnType<typeof useUploadMutations> | undefined;
  function Probe() {
    upload = useUploadMutations({ onFileStatusChange: () => {} });
    return null;
  }
  try {
    await act(async () =>
      root.render(
        <ApolloProvider client={client}>
          <Probe />
        </ApolloProvider>
      )
    );
    await act(async () =>
      upload!.uploadFiles([
        {
          file: new File(["public sample"], "sample.pdf"),
          formData: { title, description: "Public sample", slug: "" },
          status: "pending",
        },
      ])
    );
    expect(
      (await client.query(query)).data.documents.edges.map(
        (edge: { node: { title: string } }) => edge.node.title
      )
    ).toEqual([title]);
  } finally {
    await act(async () => root.unmount());
    host.remove();
    client.stop();
    cache.restore({});
  }
});

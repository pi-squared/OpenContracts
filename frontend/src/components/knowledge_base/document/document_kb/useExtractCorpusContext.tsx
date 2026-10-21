import React, { useEffect, useRef, useState } from "react";
import { gql, useApolloClient, ApolloQueryResult } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from "@os-legal/ui";
import { getDocumentUrl } from "../../../../utils/navigationUtils";
import { DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS } from "../LayoutComponents";

export const GET_DOCUMENT_EXTRACT_CORPORA = gql`
  query GetDocumentExtractCorpora($documentId: ID!, $after: String) {
    document(id: $documentId) {
      id
      slug
      creator {
        slug
      }
      pathRecords(first: 100, after: $after) {
        edges {
          node {
            isCurrent
            isDeleted
            corpus {
              id
              title
              slug
              creator {
                slug
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
`;

type CorpusContext = {
  id: string;
  title: string;
  slug: string;
  creator: { slug: string };
};
type MembershipData = {
  document: {
    id: string;
    slug: string;
    creator: { slug: string };
    pathRecords: {
      edges: ({
        node: {
          isCurrent: boolean;
          isDeleted: boolean;
          corpus: CorpusContext;
        } | null;
      } | null)[];
      pageInfo: { hasNextPage: boolean; endCursor: string | null };
    };
  } | null;
};
type Choice = { corpus: CorpusContext; url: string };

/** Resolve context, never create membership. Corpus-qualified navigation lets
 * CentralRouteManager supply the same context as entry through a corpus. */
export function useExtractCorpusContext(
  documentId: string,
  corpusId: string | undefined,
  onUnassigned: () => void
) {
  const client = useApolloClient();
  const navigate = useNavigate();
  const location = useLocation();
  const generation = useRef(0);
  const [status, setStatus] = useState<
    "closed" | "loading" | "choice" | "error"
  >("closed");
  const [choices, setChoices] = useState<Choice[]>([]);

  useEffect(() => {
    setStatus("closed");
    setChoices([]);
    return () => {
      generation.current++;
    };
  }, [documentId, corpusId]);

  const close = () => {
    generation.current++;
    setStatus("closed");
  };
  const select = (choice: Choice) => {
    close();
    navigate(
      { pathname: choice.url, search: location.search },
      {
        state: { openDocumentExtracts: documentId },
        replace: true,
      }
    );
  };
  const resolve = async () => {
    const request = ++generation.current;
    setStatus("loading");
    try {
      const corpora = new Map<string, Choice>();
      let after: string | null = null;
      do {
        // no-cache keeps a previous visit (or a partial page) from deciding
        // whether this document still has a current accessible membership.
        const response: ApolloQueryResult<MembershipData> =
          await client.query<MembershipData>({
            query: GET_DOCUMENT_EXTRACT_CORPORA,
            variables: { documentId, after },
            fetchPolicy: "no-cache",
            errorPolicy: "none",
          });
        const data: MembershipData = response.data;
        if (request !== generation.current) return;
        if (!data.document) throw new Error("Document unavailable");
        const { pathRecords } = data.document;
        for (const edge of pathRecords.edges) {
          const path = edge?.node;
          if (!path?.isCurrent || path.isDeleted) continue;
          const corpus = path.corpus;
          // Do not silently fall back to a standalone URL if slugs are absent.
          if (
            !corpus.slug ||
            !corpus.creator?.slug ||
            !data.document.slug ||
            !data.document.creator?.slug
          )
            throw new Error("Corpus context unavailable");
          corpora.set(corpus.id, {
            corpus,
            url: getDocumentUrl(data.document, corpus),
          });
        }
        const { hasNextPage, endCursor } = pathRecords.pageInfo;
        if (hasNextPage && (!endCursor || endCursor === after))
          throw new Error("Incomplete corpus memberships");
        after = hasNextPage ? endCursor : null;
      } while (after);
      const available = [...corpora.values()];
      if (available.length === 1) select(available[0]);
      else if (available.length > 1) {
        setChoices(available);
        setStatus("choice");
      } else {
        close();
        onUnassigned();
      }
    } catch {
      if (request === generation.current) setStatus("error");
    }
  };

  return {
    resolve,
    dialog: (
      <Modal
        open={status !== "closed"}
        onClose={close}
        size="sm"
        overlayClassName={DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS}
      >
        <ModalHeader title="Choose a corpus for extracts" />
        <ModalBody>
          {status === "loading" && (
            <p role="status">Loading corpus memberships…</p>
          )}
          {status === "error" && (
            <p role="alert">Unable to load corpus memberships. Please retry.</p>
          )}
          {status === "choice" && (
            <>
              <p>
                This document belongs to several corpuses. Choose one to view
                its extracts.
              </p>
              {choices.map((choice) => (
                <Button key={choice.corpus.id} onClick={() => select(choice)}>
                  {choice.corpus.title}
                </Button>
              ))}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          {status === "error" && <Button onClick={resolve}>Retry</Button>}
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
    ),
  };
}

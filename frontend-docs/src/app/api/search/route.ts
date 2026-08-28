import { createFromSource } from "fumadocs-core/search/server";
import { source } from "@/lib/docs-source";

// A static export has no server to answer a request-time search query, so
// this exports the full search index as a pre-built JSON file instead --
// `staticGET` (aliased as the route's `GET`) is fumadocs' own static-export
// counterpart to the dynamic search handler; the client swaps to a matching
// static search client (`fumadocs-core/search/client/orama-static`), which
// runs the actual search in the browser against this file.
export const revalidate = false;
export const { staticGET: GET } = createFromSource(source);

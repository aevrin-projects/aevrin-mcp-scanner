import { loader } from "fumadocs-core/source";
import { docs } from "../../.source/server";

// This whole app is the docs site, so it serves content at its own root
// rather than under a /docs prefix.
export const source = loader({
  baseUrl: "/",
  source: docs.toFumadocsSource(),
});

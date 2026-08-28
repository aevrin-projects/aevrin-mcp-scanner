"use client";

import {
  SearchDialog,
  SearchDialogClose,
  SearchDialogContent,
  SearchDialogHeader,
  SearchDialogIcon,
  SearchDialogInput,
  SearchDialogList,
  SearchDialogOverlay,
  type SharedProps,
} from "fumadocs-ui/components/dialog/search";
import { useDocsSearch } from "fumadocs-core/search/client";
import { staticClient } from "fumadocs-core/search/client/orama-static";

/**
 * The default search dialog fetches `/api/search` per keystroke and expects
 * the server to filter by query. A static export can't do that -- there is
 * no server at request time -- so `/api/search` instead serves the whole
 * index once (see that route's `staticGET`), and this component runs the
 * actual query client-side against it via Orama.
 */
export default function DocsSearchDialog(props: SharedProps) {
  const { search, setSearch, query } = useDocsSearch({
    client: staticClient(),
  });

  return (
    <SearchDialog search={search} onSearchChange={setSearch} isLoading={query.isLoading} {...props}>
      <SearchDialogOverlay />
      <SearchDialogContent>
        <SearchDialogHeader>
          <SearchDialogIcon />
          <SearchDialogInput />
          <SearchDialogClose />
        </SearchDialogHeader>
        <SearchDialogList items={query.data !== "empty" ? query.data : null} />
      </SearchDialogContent>
    </SearchDialog>
  );
}

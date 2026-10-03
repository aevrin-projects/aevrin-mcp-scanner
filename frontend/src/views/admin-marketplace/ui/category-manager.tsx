"use client";

import { useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";

import { marketplaceAdminApi } from "@/entities/admin";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/shared/ui";

type Category = { slug: string; name: string; description: string | null; sort_order: number };

/**
 * The registry's categories. Deleting one is refused by the API while any
 * item is filed under it, and that refusal is shown here verbatim: categories
 * are slugs on the item rather than a foreign key, so a deleted category in
 * use would leave items filed somewhere nothing can browse to.
 */
export function CategoryManager({ onChanged }: { onChanged: () => void }) {
  // null while not known (not loaded yet, or the load failed), so "No
  // categories yet" is shown only for a list the API returned empty.
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    marketplaceAdminApi
      .categories()
      .then((rows) => !cancelled && setCategories(rows))
      .catch(() => !cancelled && setCategories(null));
    return () => {
      cancelled = true;
    };
  }, [version]);

  async function run(key: string, fn: () => Promise<unknown>, done: string) {
    setBusy(key);
    setMessage(null);
    try {
      await fn();
      setMessage(done);
      setVersion((n) => n + 1);
      onChanged();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Categories</PanelTitle>
      </PanelHeader>
      <PanelBody className="space-y-3">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!slug) return;
            void run(
              "new",
              () => marketplaceAdminApi.saveCategory({ slug, name: name.trim(), sort_order: 500 }),
              `Category "${name.trim()}" saved.`,
            ).then(() => setName(""));
          }}
        >
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="New category name"
            aria-label="New category name"
            className="min-w-[200px] flex-1"
          />
          <Button type="submit" size="sm" disabled={!slug || busy === "new"}>
            {busy === "new" ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : null}
            Add
          </Button>
        </form>
        {message ? (
          <p className="text-xs text-muted-foreground" role="status">
            {message}
          </p>
        ) : null}
        {categories?.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No categories yet. An item can be filed only under a category that exists, so add one first.
          </p>
        ) : null}
        <ul className="flex flex-wrap gap-1.5">
          {(categories ?? []).map((category) => (
            <li
              key={category.slug}
              className="inline-flex items-center gap-1 rounded-md border border-border py-0.5 pr-0.5 pl-2 text-xs"
            >
              {category.name}
              <button
                type="button"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:opacity-50"
                aria-label={`Delete category ${category.name}`}
                disabled={busy === category.slug}
                onClick={() =>
                  void run(
                    category.slug,
                    () => marketplaceAdminApi.deleteCategory(category.slug),
                    `Category "${category.name}" deleted.`,
                  )
                }
              >
                <Trash2 className="size-3" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      </PanelBody>
    </Panel>
  );
}

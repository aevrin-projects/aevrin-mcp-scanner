import type { ReactNode } from "react";
import { Reveal } from "@/shared/ui/reveal";

/**
 * Folio's section header: a mono eyebrow, then the serif h2 on the left and a
 * muted lede bottom-aligned on the right. Never centred, except where a
 * section is a single column (pricing), which passes `centered`.
 */
export function SectionHeader({
  id,
  eyebrow,
  title,
  lede,
  centered = false,
}: {
  /** Put on the h2, for `aria-labelledby` on the section. */
  id: string;
  eyebrow?: string;
  title: ReactNode;
  lede: ReactNode;
  centered?: boolean;
}) {
  if (centered) {
    return (
      <Reveal className="mx-auto max-w-2xl text-center">
        {eyebrow ? <p className="mk-eyebrow">{eyebrow}</p> : null}
        <h2 id={id} className="mk-h2 mt-4">
          {title}
        </h2>
        <p className="mk-lede mx-auto mt-5 max-w-xl">{lede}</p>
      </Reveal>
    );
  }

  return (
    <Reveal>
      {eyebrow ? <p className="mk-eyebrow">{eyebrow}</p> : null}
      <div className="mt-4 grid items-end gap-5 md:grid-cols-2 md:gap-12">
        <h2 id={id} className="mk-h2">
          {title}
        </h2>
        <p className="mk-lede max-w-xl">{lede}</p>
      </div>
    </Reveal>
  );
}

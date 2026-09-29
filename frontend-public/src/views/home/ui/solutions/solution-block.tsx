"use client";

import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import styles from "./solutions.module.css";
import { useEntrance } from "./use-sequence";

export type SeeAlsoLink = { label: string; href: string };

function Entrance({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const { ref, hidden } = useEntrance<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={cn(styles.enter, className)}
      data-state={hidden ? "hidden" : "shown"}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}

/**
 * One numbered block: copy in one column, the product mockup in the other,
 * alternating sides from block to block on wide screens. Below `lg` the copy
 * always comes first, so a phone reads the claim before the illustration.
 */
export function SolutionBlock({
  id,
  eyebrow,
  title,
  body,
  aside,
  seeAlso,
  mockup,
  mockupFirst = false,
}: {
  id: string;
  eyebrow: string;
  title: string;
  body: ReactNode;
  aside?: ReactNode;
  seeAlso: SeeAlsoLink[];
  mockup: ReactNode;
  mockupFirst?: boolean;
}) {
  const headingId = `${id}-title`;
  return (
    <article
      aria-labelledby={headingId}
      className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16"
    >
      <Entrance className={cn("min-w-0 max-w-xl", mockupFirst && "lg:order-2 lg:justify-self-end")}>
        <p className={cn("mk-eyebrow", styles.eyebrow)}>{eyebrow}</p>
        <h3 id={headingId} className={cn("mk-h2", styles.title, "mt-4")}>
          {title}
        </h3>
        <div className={cn(styles.body, "mt-5 space-y-4")}>{body}</div>
        {aside ? <div className="mt-8">{aside}</div> : null}
        <div className="mt-8">
          <p className="text-sm font-medium" style={{ color: "var(--mk-fg)" }}>
            See also
          </p>
          <ul className="mt-2.5 space-y-2">
            {seeAlso.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className={cn(styles.seeLink, "inline-flex items-start gap-1.5 text-sm")}
                >
                  <ArrowUpRight className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                  <span>{link.label}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      </Entrance>
      <Entrance delay={80} className={cn("min-w-0", mockupFirst && "lg:order-1")}>
        {mockup}
      </Entrance>
    </article>
  );
}

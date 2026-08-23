import * as React from "react";
import { cn } from "@/shared/lib/utils";
import { Panel, PanelActions, PanelBody, PanelHeader, PanelSubtitle, PanelTitle } from "./panel";

/**
 * The common panel arrangement: titled header with one optional action, body
 * below. Most screens want exactly this, so it exists as one component rather
 * than four lines repeated everywhere; reach for the Panel parts directly when
 * a section needs a footer, a full-bleed table, or a custom header row.
 */
export function SectionCard({
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
  style,
  /** Drop the body padding for a full-bleed table or list. */
  flush = false,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  style?: React.CSSProperties;
  flush?: boolean;
}) {
  return (
    <Panel className={className} style={style}>
      <PanelHeader className={description ? "items-start" : undefined}>
        <div className="min-w-0">
          <PanelTitle>{title}</PanelTitle>
          {description ? <PanelSubtitle>{description}</PanelSubtitle> : null}
        </div>
        {action ? <PanelActions>{action}</PanelActions> : null}
      </PanelHeader>
      {flush ? (
        <div className={cn("flex-1", bodyClassName)}>{children}</div>
      ) : (
        <PanelBody className={bodyClassName}>{children}</PanelBody>
      )}
    </Panel>
  );
}

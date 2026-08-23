import defaultMdxComponents from "fumadocs-ui/mdx";
import { Card, Cards } from "fumadocs-ui/components/card";
import { Tab, Tabs } from "fumadocs-ui/components/tabs";
import { Step, Steps } from "fumadocs-ui/components/steps";
import { Accordion, Accordions } from "fumadocs-ui/components/accordion";
import { Callout } from "fumadocs-ui/components/callout";
import type { MDXComponents } from "mdx/types";
import type { TableHTMLAttributes } from "react";

function AccessibleTable(props: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div
      className="relative my-6 overflow-auto rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fd-ring"
      tabIndex={0}
      role="region"
      aria-label="Scrollable data table"
    >
      <table {...props} />
    </div>
  );
}

export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    Card,
    Cards,
    Tab,
    Tabs,
    Step,
    Steps,
    Accordion,
    Accordions,
    Callout,
    table: AccessibleTable,
    ...components,
  };
}

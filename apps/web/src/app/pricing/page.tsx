import type { Metadata } from "next";
import { PricingSection } from "@/components/pricing-section";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = {
  title: "Pricing — Aevrin",
  description: "Compare Aevrin's Free, Hobby, and Team MCP security scanning plans.",
};

export default function PricingPage() {
  return (
    <div>
      <PricingSection headingLevel="h1" />
      <SiteFooter />
    </div>
  );
}

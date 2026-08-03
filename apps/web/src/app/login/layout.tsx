import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign in — Aevrin",
  description: "Sign in to the Aevrin MCP security scanning workspace.",
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}

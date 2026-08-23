import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "System Status: Aevrin",
  description: "Live availability checks for Aevrin's public web, API, authentication, and reporting services.",
};

export { StatusPage as default } from "@/views/status";

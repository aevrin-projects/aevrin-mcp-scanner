import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "CLI Setup: Aevrin",
  description: "Install the Aevrin CLI, sign in securely, and configure the Claude Code hook.",
};

export { CliPage as default } from "@/views/cli";

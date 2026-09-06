import type { Metadata } from "next";
import { AdminGate } from "@/features/admin-gate";
import { AdminShell } from "@/widgets/admin-shell";

export const metadata: Metadata = {
  title: "Admin: Aevrin",
  // The panel must never be indexed, and X-Robots-Tag via metadata is the
  // belt to robots.txt's braces (which only stops well-behaved crawlers).
  robots: { index: false, follow: false, nocache: true },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <AdminShell>{children}</AdminShell>
    </AdminGate>
  );
}

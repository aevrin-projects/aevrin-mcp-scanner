import type { Metadata } from "next";
import Link from "next/link";
import { AdminGate } from "./admin-gate";

export const metadata: Metadata = {
  title: "Admin — Aevrin",
  // The panel must never be indexed, and X-Robots-Tag via metadata is the
  // belt to robots.txt's braces (which only stops well-behaved crawlers).
  robots: { index: false, follow: false, nocache: true },
};

const NAV = [
  { href: "/admin", label: "Users" },
  { href: "/admin/audit", label: "Audit log" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGate>
      <div className="min-h-svh bg-background">
        <header className="border-b border-border">
          <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-6 py-3">
            <Link href="/admin" className="text-sm font-semibold tracking-tight">
              Aevrin <span className="text-muted-foreground">admin</span>
            </Link>
            <nav className="flex items-center gap-4">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <Link
              href="/dashboard"
              className="ml-auto text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              Back to product →
            </Link>
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] px-6 py-8">{children}</main>
      </div>
    </AdminGate>
  );
}

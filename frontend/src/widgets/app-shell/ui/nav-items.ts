import {
  Blocks,
  Bot,
  Laptop,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  ChartNoAxesCombined,
  CreditCard,
  History,
  KeyRound,
  LayoutDashboard,
  Plug,
  ScanSearch,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  /** True when the route also matches its children, so /agents does not stay
   *  highlighted while /agents/mcp is open. */
  exact?: boolean;
}

export interface NavGroup {
  label: string | null;
  items: NavItem[];
}

/**
 * Only routes that exist. A sidebar entry is a promise that something is on
 * the other side of it, and the fastest way to make a security product feel
 * untrustworthy is to have half its navigation lead nowhere.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [{ href: "/dashboard", label: "Overview", icon: LayoutDashboard }],
  },
  {
    label: "AI security",
    items: [
      { href: "/agents", label: "Agents", icon: Bot, exact: true },
      { href: "/agents/devices", label: "Devices", icon: Laptop },
      { href: "/agents/mcp", label: "MCP servers", icon: Blocks },
      { href: "/agents/skills", label: "Skills", icon: Sparkles },
      { href: "/agents/permissions", label: "Permissions", icon: ShieldCheck },
      { href: "/agents/attack-paths", label: "Attack paths", icon: ShieldAlert },
      { href: "/agents/policies", label: "Policies", icon: Scale },
    ],
  },
  {
    label: "Scanning",
    items: [
      { href: "/scans/new", label: "New scan", icon: ScanSearch },
      { href: "/scans/history", label: "History", icon: History },
    ],
  },
  {
    label: "Automation",
    items: [{ href: "/integrations", label: "Hooks and CI", icon: Plug }],
  },
  {
    label: "Account",
    items: [
      { href: "/usage", label: "Usage", icon: ChartNoAxesCombined },
      { href: "/settings/api-keys", label: "API keys", icon: KeyRound },
      { href: "/settings/billing", label: "Billing", icon: CreditCard },
    ],
  },
];

export function isActivePath(pathname: string, item: NavItem) {
  return item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
}

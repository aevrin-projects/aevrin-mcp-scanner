import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";

export const baseOptions: BaseLayoutProps = {
  nav: {
    title: (
      <span className="flex items-center gap-2 font-semibold">
        <img src="/logo.png" alt="" width={20} height={22} />
        Aevrin
      </span>
    ),
  },
  links: [
    {
      text: "Home",
      url: "https://mcp.aevrin.net",
    },
    {
      text: "Dashboard",
      url: "https://mcp.aevrin.net/dashboard",
    },
    {
      text: "Support",
      url: "mailto:support@aevrin.net",
    },
  ],
};

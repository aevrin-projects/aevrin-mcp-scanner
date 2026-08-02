"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";

const emptySubscribe = () => () => {};

// next-themes 0.4 resolves `resolvedTheme` synchronously on the client's
// first paint (via its own useSyncExternalStore), which no longer matches
// the server's render — so an explicit mounted flag, not resolvedTheme
// itself, has to gate which icon renders to avoid a hydration mismatch.
// useSyncExternalStore (rather than a useState+useEffect pair) is the
// lint-clean way to get that flag: it returns the server snapshot (false)
// for the SSR-matching first render, then true once mounted client-side.
function useHasMounted() {
  return useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useHasMounted();

  const isDark = mounted && resolvedTheme === "dark";

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label="Toggle theme"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}

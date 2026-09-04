import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { LogOutIcon, MoonIcon, SunIcon, UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SyncCard } from "@/components/dashboard/SyncCard";
import { Toaster } from "@/components/ui/sonner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth, useLogout } from "@/lib/auth";
import { useSettings } from "@/lib/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard" },
  { to: "/board", label: "Draft Board" },
  { to: "/draft", label: "Live Draft" },
  { to: "/keeper", label: "Keepers" },
];

const THEME_KEY = "ffdraft-theme";

function useTheme() {
  const [dark, setDark] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      if (stored === "dark") return true;
      if (stored === "light") return false;
    } catch {
      // ignore
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
    } catch {
      // ignore
    }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function StatusDot() {
  const { data, isError } = useSettings();
  const ready = !!data?.ready;
  const label = isError ? "Server unreachable" : ready ? "League data ready — click to sync or refresh" : "Not synced yet — click to sync";
  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <button type="button" className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">
              <span
                className={cn(
                  "inline-block size-2 rounded-full",
                  isError ? "bg-destructive" : ready ? "bg-emerald-500" : "bg-amber-500",
                )}
              />
              <span className="hidden sm:inline">{ready ? "Ready" : isError ? "Offline" : "Not synced"}</span>
            </button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" className="w-[min(40rem,calc(100vw-2rem))] p-0">
        <SyncCard />
      </PopoverContent>
    </Popover>
  );
}

function UserMenu() {
  const { user } = useAuth();
  const logout = useLogout();
  const navigate = useNavigate();
  if (!user) return null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-1.5 px-2">
          <UserIcon className="size-4" />
          <span className="hidden sm:inline">{user.username}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-52 p-1">
        <NavLink
          to="/account"
          className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-muted"
        >
          <UserIcon className="size-4" />
          Account{user.is_admin && " & members"}
        </NavLink>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login", { replace: true }) })}
        >
          <LogOutIcon className="size-4" />
          Sign out
        </button>
      </PopoverContent>
    </Popover>
  );
}

export function AppShell() {
  const { dark, toggle } = useTheme();
  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex min-h-screen flex-col">
        <header className="print-hide sticky top-0 z-40 border-b bg-background/90 backdrop-blur supports-backdrop-filter:bg-background/70">
          <div className="mx-auto flex h-12 w-full max-w-screen-2xl items-center gap-4 px-4">
            <span className="font-heading text-sm font-semibold tracking-tight">FF Draft</span>
            <nav className="flex items-center gap-1">
              {NAV.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.to === "/"}
                  className={({ isActive }) =>
                    cn(
                      "rounded-md px-2.5 py-1.5 text-sm transition-colors",
                      isActive ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
                    )
                  }
                >
                  {n.label}
                </NavLink>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-3">
              <StatusDot />
              <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Toggle theme">
                {dark ? <SunIcon /> : <MoonIcon />}
              </Button>
              <UserMenu />
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-5">
          <Outlet />
        </main>
      </div>
      <Toaster position="bottom-right" richColors />
    </TooltipProvider>
  );
}

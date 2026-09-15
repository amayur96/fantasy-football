import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { ChevronDownIcon, LayoutGridIcon, LogOutIcon, MoonIcon, StarIcon, SunIcon, UserIcon, ZapIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SyncCard } from "@/components/dashboard/SyncCard";
import { Toaster } from "@/components/ui/sonner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth, useLogout } from "@/lib/auth";
import { useSettings } from "@/lib/queries";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const NAV = [{ to: "/", label: "Dashboard" }];

const DRAFT_TOOLS = [
  { to: "/draft", label: "Live Draft", icon: ZapIcon, hint: "Pick-by-pick board with recommendations", end: true },
  { to: "/draft/board", label: "Board", icon: LayoutGridIcon, hint: "Every team's picks, synced with the sheet" },
  { to: "/draft/keepers", label: "Keepers", icon: StarIcon, hint: "Keeper costs and your draft slot" },
];

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-md px-2.5 py-1.5 text-sm transition-colors",
    isActive ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
  );

function DraftToolsMenu() {
  const [open, setOpen] = useState(false);
  // The trigger is not itself a link, so it has to read the URL to show as the active tab.
  const active = useLocation().pathname.startsWith("/draft");
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-sm transition-colors",
            active ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          Draft Tools
          <ChevronDownIcon className={cn("size-3.5 transition-transform", open && "rotate-180")} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-1">
        {DRAFT_TOOLS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              cn("flex items-start gap-2 rounded-sm px-2 py-1.5 hover:bg-muted", isActive && "bg-muted")
            }
          >
            <t.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span className="flex flex-col">
              <span className="text-sm font-medium">{t.label}</span>
              <span className="text-xs text-muted-foreground">{t.hint}</span>
            </span>
          </NavLink>
        ))}
      </PopoverContent>
    </Popover>
  );
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
  const { data: settings } = useSettings();
  const logout = useLogout();
  const navigate = useNavigate();
  if (!user) return null;
  const team = settings?.settings?.teams.find((t) => t.team_id === user.team_id)?.name;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-1.5 px-2">
          <UserIcon className="size-4" />
          <span className="hidden sm:inline">{team ?? user.username}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-1">
        {team && <p className="px-2 pt-1 pb-1.5 text-xs text-muted-foreground">{user.username} · {team}</p>}
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
            <span className="font-heading text-sm font-semibold tracking-tight">FF</span>
            <nav className="flex items-center gap-1">
              {NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === "/"} className={navLinkClass}>
                  {n.label}
                </NavLink>
              ))}
              <DraftToolsMenu />
            </nav>
            <div className="ml-auto flex items-center gap-3">
              <StatusDot />
              <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
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

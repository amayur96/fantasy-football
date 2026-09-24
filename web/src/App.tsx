import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/components/AuthProvider";
import { RequireAuth } from "@/components/RequireAuth";
import { RequireTeam } from "@/components/RequireTeam";
import { Account } from "@/pages/Account";
import { Board } from "@/pages/Board";
import { LiveDraft } from "@/pages/LiveDraft";
import { Dashboard } from "@/pages/Dashboard";
import { Waivers } from "@/pages/Waivers";
import { Keeper } from "@/pages/Keeper";
import { Login } from "@/pages/Login";
import { Join } from "@/pages/Join";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="login" element={<Login />} />
            <Route path="join" element={<Join />} />
            <Route element={<RequireAuth />}>
              <Route element={<RequireTeam />}>
                <Route element={<AppShell />}>
                <Route index element={<Dashboard />} />
                <Route path="waivers" element={<Waivers />} />
                <Route path="draft" element={<LiveDraft />} />
                <Route path="draft/board" element={<Board />} />
                <Route path="draft/keepers" element={<Keeper />} />
                <Route path="account" element={<Account />} />
                {/* Bookmarks and printed cheat sheets from before the draft tools moved. */}
                <Route path="board" element={<Navigate to="/draft/board" replace />} />
                <Route path="keeper" element={<Navigate to="/draft/keepers" replace />} />
                </Route>
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

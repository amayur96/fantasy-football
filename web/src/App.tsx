import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";
import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/components/AuthProvider";
import { RequireAuth } from "@/components/RequireAuth";
import { Account } from "@/pages/Account";
import { Board } from "@/pages/Board";
import { LiveDraft } from "@/pages/LiveDraft";
import { Dashboard } from "@/pages/Dashboard";
import { Keeper } from "@/pages/Keeper";
import { Login } from "@/pages/Login";

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
            <Route element={<RequireAuth />}>
              <Route element={<AppShell />}>
                <Route index element={<Dashboard />} />
                <Route path="keeper" element={<Keeper />} />
                <Route path="board" element={<Board />} />
                <Route path="draft" element={<LiveDraft />} />
                <Route path="account" element={<Account />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

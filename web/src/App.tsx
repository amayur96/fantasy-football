import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";
import { AppShell } from "@/components/AppShell";
import { Board } from "@/pages/Board";
import { LiveDraft } from "@/pages/LiveDraft";
import { Dashboard } from "@/pages/Dashboard";
import { Keeper } from "@/pages/Keeper";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Dashboard />} />
            <Route path="keeper" element={<Keeper />} />
            <Route path="board" element={<Board />} />
            <Route path="draft" element={<LiveDraft />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

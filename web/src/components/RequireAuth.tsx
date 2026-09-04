import { Navigate, Outlet, useLocation } from "react-router";
import { LoaderCircleIcon } from "lucide-react";
import { useAuth } from "@/lib/auth";

/** Sends anyone without a session to /login, remembering where they were headed. */
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoaderCircleIcon className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}

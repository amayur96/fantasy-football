import { useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, isUnauthorized, UNAUTHORIZED_EVENT } from "@/lib/api";
import { AuthContext, authKeys, type PublicUser } from "@/lib/auth";

/** Holds the signed-in user for the whole app and clears it the moment a request 401s. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: authKeys.me,
    queryFn: () => apiGet<PublicUser>("/auth/me"),
    // A 401 is the answer, not a failure: it just means "nobody is signed in".
    retry: (count, err) => !isUnauthorized(err) && count < 1,
    staleTime: 60_000,
  });

  // If any request 401s (an expired session, say), drop the cached identity so the guard redirects.
  useEffect(() => {
    const onUnauthorized = () => qc.setQueryData(authKeys.me, null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [qc]);

  return <AuthContext.Provider value={{ user: data ?? null, loading: isPending }}>{children}</AuthContext.Provider>;
}

import { Outlet, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth, useLogout } from "@/lib/auth";

/**
 * Everything inside the app is about *your* team. Members never choose one themselves — it comes
 * from the invite link — so an account with no team (added by hand, or moved off a team) waits here.
 * Admins pass through: the server treats them as the cookie owner's team until they assign one.
 */
export function RequireTeam() {
  const { user } = useAuth();
  const logout = useLogout();
  const navigate = useNavigate();
  if (user && user.team_id === null && !user.is_admin) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 py-10">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="font-heading">No team linked yet</CardTitle>
            <CardDescription>
              Your account ({user.username}) is not tied to a team in the league, so there is nothing to show. The tool's admin can
              link it from their Account page — or send you a fresh invite link.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" disabled={logout.isPending} onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login", { replace: true }) })}>
              Sign out
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  return <Outlet />;
}

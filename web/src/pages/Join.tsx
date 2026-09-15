import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { LoaderCircleIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useAuth, useInviteInfo, useJoin, useLogout } from "@/lib/auth";

/** /join?token=… — the link an admin sends. The team is fixed by the link; the person only picks a login. */
export function Join() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { user } = useAuth();
  const navigate = useNavigate();
  const logout = useLogout();
  const info = useInviteInfo(token);
  const join = useJoin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);

  // A test invite is safe to walk through while signed in — it creates nothing. A real one creates
  // a *new* account, so the current session has to go first; redirecting home would just look broken.
  if (user && !join.isSuccess && info.data?.valid && !info.data.test) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 py-10">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="font-heading">You are already signed in</CardTitle>
            <CardDescription>
              This invite creates a new account{info.data?.valid ? ` for ${info.data.team_name}` : ""}, but you are signed in as{" "}
              <span className="font-medium text-foreground">{user.username}</span>. Sign out here, or open the link in a private window.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2">
            <Button disabled={logout.isPending} onClick={() => logout.mutate()}>
              Sign out and continue
            </Button>
            <Button variant="outline" onClick={() => navigate("/", { replace: true })}>
              Stay signed in
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    join.mutate({ token: token ?? "", username: username.trim(), password }, { onSuccess: (r) => !r.test && navigate("/", { replace: true }) });
  }

  if (join.isSuccess && join.data.test) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 py-10">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="font-heading">Test complete</CardTitle>
            <CardDescription>{join.data.message}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => navigate("/", { replace: true })}>Back to the app</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const error = mismatch ? "Passwords do not match." : join.error ? errorMessage(join.error) : null;
  const bad = !token ? "This link is missing its invite token." : info.data && !info.data.valid ? info.data.reason : info.error ? errorMessage(info.error) : null;

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="font-heading">{info.data?.valid ? `Join ${info.data.league_name || "the league"}` : "Join the league tool"}</CardTitle>
          <CardDescription>
            {info.data?.valid
              ? `This invite is for ${info.data.team_name}. Your account will be tied to that team — if that is not yours, tell the tool's admin before continuing. Just pick a username and password.`
              : "Create your account from the invite you were sent."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {info.isLoading && <Skeleton className="h-40 w-full" />}
          {bad && (
            <Alert variant="destructive">
              <AlertDescription>{bad}</AlertDescription>
            </Alert>
          )}
          {info.data?.valid && (
            <form className="grid gap-4" onSubmit={onSubmit}>
              <div className="grid gap-1.5">
                <label htmlFor="username" className="text-sm font-medium">
                  Username
                </label>
                <Input id="username" name="username" autoComplete="username" autoFocus required value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="grid gap-1.5">
                <label htmlFor="password" className="text-sm font-medium">
                  Password
                </label>
                <Input id="password" name="password" type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <div className="grid gap-1.5">
                <label htmlFor="confirm" className="text-sm font-medium">
                  Confirm password
                </label>
                <Input id="confirm" name="confirm" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </div>
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Button type="submit" disabled={join.isPending}>
                {join.isPending && <LoaderCircleIcon className="animate-spin" />}
                Create my account
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

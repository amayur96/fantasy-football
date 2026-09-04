import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";
import { LoaderCircleIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { useAuth, useAuthStatus, useLogin, useRegister } from "@/lib/auth";

export function Login() {
  const location = useLocation();
  const { user, loading } = useAuth();
  const { data: status } = useAuthStatus();
  const login = useLogin();
  const register = useRegister();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);

  // No accounts yet? The first person to arrive sets up the admin account.
  const firstRun = status?.users_exist === false;
  const canRegister = firstRun || !!status?.allow_registration;
  const [signingUp, setSigningUp] = useState(false);
  const creating = firstRun || (canRegister && signingUp);
  const action = creating ? register : login;

  if (!loading && user) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? "/"} replace />;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (creating && password !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    action.mutate({ username: username.trim(), password });
  }

  const error = mismatch ? "Passwords do not match." : action.error ? errorMessage(action.error) : null;

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="font-heading">{creating ? "Create your account" : "Sign in"}</CardTitle>
          <CardDescription>
            {firstRun
              ? "No accounts exist yet — this first one becomes the admin."
              : creating
                ? "Pick a username and a password of at least 4 characters."
                : "FF Draft Assistant"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={onSubmit}>
            <div className="grid gap-1.5">
              <label htmlFor="username" className="text-sm font-medium">
                Username
              </label>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={creating ? "new-password" : "current-password"}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {creating && (
              <div className="grid gap-1.5">
                <label htmlFor="confirm" className="text-sm font-medium">
                  Confirm password
                </label>
                <Input
                  id="confirm"
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </div>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" disabled={action.isPending}>
              {action.isPending && <LoaderCircleIcon className="animate-spin" />}
              {creating ? "Create account" : "Sign in"}
            </Button>
            {canRegister && !firstRun && (
              <button
                type="button"
                className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                onClick={() => {
                  setSigningUp((s) => !s);
                  setMismatch(false);
                  action.reset();
                }}
              >
                {signingUp ? "Already have an account? Sign in" : "Need an account? Create one"}
              </button>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

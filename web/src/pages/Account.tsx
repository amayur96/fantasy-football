import { useState, type FormEvent } from "react";
import { LoaderCircleIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api";
import { useAddUser, useAuth, useChangePassword, useDeleteUser, useUsers } from "@/lib/auth";

function ChangePassword() {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (next !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          toast.success("Password updated");
          setCurrent("");
          setNext("");
          setConfirm("");
        },
      },
    );
  }

  const error = mismatch ? "New passwords do not match." : change.error ? errorMessage(change.error) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
        <CardDescription>At least 4 characters.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid max-w-sm gap-4" onSubmit={onSubmit}>
          <div className="grid gap-1.5">
            <label htmlFor="current" className="text-sm font-medium">
              Current password
            </label>
            <Input id="current" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <label htmlFor="next" className="text-sm font-medium">
              New password
            </label>
            <Input id="next" type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <label htmlFor="confirm-new" className="text-sm font-medium">
              Confirm new password
            </label>
            <Input id="confirm-new" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </div>
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-fit" disabled={change.isPending}>
            {change.isPending && <LoaderCircleIcon className="animate-spin" />}
            Update password
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ManageUsers({ myId }: { myId: string }) {
  const { data: users, isLoading } = useUsers(true);
  const add = useAddUser();
  const remove = useDeleteUser();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    add.mutate(
      { username: username.trim(), password, is_admin: isAdmin },
      {
        onSuccess: (user) => {
          toast.success(`Added ${user.username}`, { description: "Share the password with them; they can change it once signed in." });
          setUsername("");
          setPassword("");
          setIsAdmin(false);
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>League members</CardTitle>
        <CardDescription>Anyone with an account can see the whole draft board.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Added</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {users?.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.username}</TableCell>
                  <TableCell>{u.is_admin ? <Badge variant="secondary">Admin</Badge> : <span className="text-muted-foreground">Member</span>}</TableCell>
                  <TableCell className="text-muted-foreground">{new Date(u.created_at).toLocaleDateString()}</TableCell>
                  <TableCell>
                    {u.id !== myId && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${u.username}`}
                        disabled={remove.isPending}
                        onClick={() => {
                          if (!window.confirm(`Remove ${u.username}? They will lose access immediately.`)) return;
                          remove.mutate(u.id, {
                            onSuccess: () => toast.success(`Removed ${u.username}`),
                            onError: (err) => toast.error(errorMessage(err)),
                          });
                        }}
                      >
                        <Trash2Icon />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <form className="grid max-w-sm gap-4 border-t pt-6" onSubmit={onSubmit}>
          <p className="text-sm font-medium">Add a member</p>
          <div className="grid gap-1.5">
            <label htmlFor="new-username" className="text-sm font-medium">
              Username
            </label>
            <Input id="new-username" required value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <label htmlFor="new-password" className="text-sm font-medium">
              Temporary password
            </label>
            <Input id="new-password" type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={isAdmin} onCheckedChange={setIsAdmin} />
            Can manage members
          </label>
          {add.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(add.error)}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-fit" disabled={add.isPending}>
            {add.isPending && <LoaderCircleIcon className="animate-spin" />}
            Add member
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function Account() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="grid max-w-3xl gap-6">
      <div>
        <h1 className="font-heading text-xl font-semibold tracking-tight">Account</h1>
        <p className="text-sm text-muted-foreground">
          Signed in as <span className="font-medium text-foreground">{user.username}</span>
          {user.is_admin && " (admin)"}
        </p>
      </div>
      <ChangePassword />
      {user.is_admin && <ManageUsers myId={user.id} />}
    </div>
  );
}

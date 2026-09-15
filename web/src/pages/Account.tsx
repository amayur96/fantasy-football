import { useState, type FormEvent } from "react";
import { FlaskConicalIcon, LoaderCircleIcon, MailIcon, PencilIcon, RotateCcwIcon, SendIcon, Trash2Icon, UserRoundXIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  useAddUser, useAuth, useAuthStatus, useChangePassword, useCreateInvite, useDeleteUser, useInvites, useLeagueTeams, useMailInfo, useResendInvite, useRevokeInvite, useSetUserTeam, useTestInvite, useUsers,
} from "@/lib/auth";
import type { LeagueTeam } from "@/lib/auth";

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

const NONE = "none";

function InviteDialog({ team, replacing, onClose }: { team: LeagueTeam | null; replacing?: string; onClose: () => void }) {
  const { data: status } = useAuthStatus();
  const create = useCreateInvite();
  const [email, setEmail] = useState("");
  const canMail = !!status?.mail_configured;
  const close = () => {
    setEmail("");
    create.reset();
    onClose();
  };
  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!team) return;
    create.mutate(
      { team_id: team.team_id, email: email.trim() },
      {
        onSuccess: (inv) => {
          toast.success(`Invite emailed to ${inv.email}`, { description: `It creates an account tied to ${inv.team_name} and works once.` });
          close();
        },
      },
    );
  }
  return (
    <Dialog open={team !== null} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{replacing ? `Send the ${team?.name} invite to a different email` : `Invite the manager of ${team?.name}`}</DialogTitle>
            <DialogDescription>
              They get an email with a one-time link. Opening it creates an account already tied to {team?.name} — the only thing they choose
              is a username and password. The link expires in two weeks.
              {team && team.owners.length > 0 && ` ESPN lists ${team.owners.join(", ")} as the manager.`}
              {replacing && ` The link already sent to ${replacing} stops working the moment this one goes out.`}
            </DialogDescription>
          </DialogHeader>
          {!canMail && (
            <Alert>
              <AlertDescription>
                Email is not set up on the server yet. Set <code className="rounded bg-muted px-1">RESEND_API_KEY</code> and{" "}
                <code className="rounded bg-muted px-1">MAIL_FROM</code> in the environment, then come back.
              </AlertDescription>
            </Alert>
          )}
          <div className="grid gap-1.5">
            <label htmlFor="invite-email" className="text-sm font-medium">
              Their email
            </label>
            <Input id="invite-email" type="email" autoComplete="off" autoFocus required placeholder="friend@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          {create.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(create.error)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button type="submit" disabled={!canMail || create.isPending || !email.trim()}>
              {create.isPending ? <LoaderCircleIcon className="animate-spin" /> : <SendIcon />} Send invite
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TestInviteDialog({ open, teamName, initialEmail, onClose }: { open: boolean; teamName: string; initialEmail: string; onClose: () => void }) {
  const send = useTestInvite();
  const [email, setEmail] = useState(initialEmail);
  const close = () => {
    send.reset();
    onClose();
  };
  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send.mutate(email.trim(), {
      onSuccess: (inv) => {
        toast.success(`Test invite emailed to ${inv.email}`, { description: "Follow the link; the last step tells you it was a test and creates nothing." });
        close();
      },
    });
  }
  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Send yourself a test invite</DialogTitle>
            <DialogDescription>
              The exact email a league-mate gets, written for {teamName}. Follow the link and fill in the form as they would; the final step says
              it was a test. Nothing is created and you stay signed in as yourself.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <label htmlFor="test-email" className="text-sm font-medium">
              Send to
            </label>
            <Input id="test-email" type="email" autoComplete="off" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          {send.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(send.error)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button type="submit" disabled={send.isPending || !email.trim()}>
              {send.isPending ? <LoaderCircleIcon className="animate-spin" /> : <FlaskConicalIcon />} Send test
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Invites() {
  const { user } = useAuth();
  const teams = useLeagueTeams();
  const invites = useInvites(true);
  const mail = useMailInfo(true);
  const { data: users } = useUsers(true);
  const revoke = useRevokeInvite();
  const resend = useResendInvite();
  const remove = useDeleteUser();
  const [target, setTarget] = useState<{ team: LeagueTeam; replacing?: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const pending = new Map((invites.data ?? []).filter((i) => i.status === "pending" && !i.test).map((i) => [i.team_id, i]));
  const myTeam = teams.data?.find((t) => t.team_id === user?.team_id) ?? null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Invite your league</CardTitle>
        <CardDescription>
          Each team's manager gets an emailed link that creates an account locked to that team, so nobody chooses — or mis-chooses — whose roster
          they see. The link is never shown here; it only exists in the email. Sent it to the wrong address? Change it. Wrong person signed up?
          Reset the team and invite again.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {mail.data && (
          <div className="rounded-lg border bg-muted/40 px-4 py-3 text-sm">
            {mail.data.configured ? (
              <>
                <p>
                  Invites go out from <span className="font-medium">{mail.data.sender}</span> via {mail.data.provider === "resend" ? "Resend" : "SMTP"}
                  {mail.data.reply_to && (
                    <>
                      ; replies come to <span className="font-medium">{mail.data.reply_to}</span>
                    </>
                  )}
                  .
                </p>
                {mail.data.link_base ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Links will start with <span className="font-mono">{mail.data.link_base}/join</span>.
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">
                    <code className="rounded bg-muted px-1">APP_URL</code> is not set, so links would point at the API and fail. Set it to this site's
                    address ({window.location.origin}) in the server environment.
                  </p>
                )}
                {mail.data.sandbox && (
                  <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                    That is Resend's sandbox sender: it only delivers to the address your Resend account is registered under. Verify a domain in
                    Resend and set <code className="rounded bg-muted px-1">MAIL_FROM</code> before inviting the league.
                  </p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button size="xs" variant="outline" disabled={!myTeam} onClick={() => setTesting(true)}>
                    <FlaskConicalIcon /> Send yourself a test invite
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    {myTeam ? `The exact email a league-mate gets, for ${myTeam.name}. Safe to follow all the way through.` : "Your account has no team yet."}
                  </span>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">
                Email is not set up: set <code className="rounded bg-muted px-1">RESEND_API_KEY</code> and <code className="rounded bg-muted px-1">MAIL_FROM</code>.
              </p>
            )}
          </div>
        )}
        {teams.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (teams.data ?? []).length === 0 ? (
          <Alert>
            <AlertDescription>No teams yet — sync the league from the status dot in the header first.</AlertDescription>
          </Alert>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Team</TableHead>
                <TableHead>ESPN manager</TableHead>
                <TableHead>Account</TableHead>
                <TableHead className="w-44" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {teams.data?.map((t) => {
                const inv = pending.get(t.team_id);
                return (
                  <TableRow key={t.team_id}>
                    <TableCell className="font-medium">{t.name}</TableCell>
                    <TableCell className="text-muted-foreground">{t.owners.join(", ") || "—"}</TableCell>
                    <TableCell>
                      {t.claimed_by ? (
                        <Badge variant="secondary">{t.claimed_by}</Badge>
                      ) : inv ? (
                        inv.send_error ? (
                          <span className="flex flex-col gap-0.5 text-xs">
                            <span className="text-rose-700 dark:text-rose-300">email failed · {inv.email}</span>
                            <span className="max-w-md text-muted-foreground">{inv.send_error}</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <MailIcon className="size-3" /> sent to {inv.email}
                            {inv.sent_at && ` · ${new Date(inv.sent_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`}
                          </span>
                        )
                      ) : (
                        <span className="text-xs text-muted-foreground">not invited</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {t.claimed_by ? (
                        t.claimed_by !== user?.username && (
                          <Button
                            variant="outline"
                            size="xs"
                            disabled={remove.isPending}
                            onClick={() => {
                              const acct = users?.find((u) => u.username === t.claimed_by);
                              if (!acct) return toast.error("Could not find that account — reload and try again.");
                              if (!window.confirm(`Reset ${t.name}? This removes ${t.claimed_by}'s account (they lose access immediately) so you can invite the right person.`)) return;
                              remove.mutate(acct.id, {
                                onSuccess: () => {
                                  toast.success(`Removed ${t.claimed_by}. ${t.name} can be invited again.`);
                                  setTarget({ team: { ...t, claimed_by: null } });
                                },
                                onError: (err) => toast.error(errorMessage(err)),
                              });
                            }}
                          >
                            <UserRoundXIcon /> Reset
                          </Button>
                        )
                      ) : inv ? (
                        <span className="inline-flex gap-1">
                          <Button
                            variant="outline"
                            size="xs"
                            disabled={resend.isPending}
                            onClick={() =>
                              resend.mutate(inv.id, { onSuccess: (r) => toast.success(`Re-sent to ${r.email}`), onError: (err) => toast.error(errorMessage(err)) })
                            }
                          >
                            <RotateCcwIcon /> Resend
                          </Button>
                          <Button variant="outline" size="xs" onClick={() => setTarget({ team: t, replacing: inv.email })}>
                            <PencilIcon /> Change email
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label="Cancel invite"
                            disabled={revoke.isPending}
                            onClick={() => revoke.mutate(inv.id, { onSuccess: () => toast.success("Invite cancelled") })}
                          >
                            <XIcon />
                          </Button>
                        </span>
                      ) : (
                        <Button size="xs" onClick={() => setTarget({ team: t })}>
                          <MailIcon /> Invite
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <InviteDialog key={target ? `${target.team.team_id}-${target.replacing ?? ""}` : "none"} team={target?.team ?? null} replacing={target?.replacing} onClose={() => setTarget(null)} />
      <TestInviteDialog key={testing ? "open" : "closed"} open={testing} teamName={myTeam?.name ?? "your team"} initialEmail={mail.data?.reply_to ?? user?.email ?? ""} onClose={() => setTesting(false)} />
    </Card>
  );
}

function TeamPicker({
  value, teams, disabled, onChange, allowTaken, self,
}: { value: number | null; teams: LeagueTeam[]; disabled?: boolean; onChange: (teamId: number | null) => void; allowTaken: boolean; self: string }) {
  return (
    <Select value={value === null ? NONE : String(value)} disabled={disabled} onValueChange={(v) => onChange(v === NONE ? null : Number(v))}>
      <SelectTrigger size="sm" className="w-56">
        <SelectValue placeholder="Choose a team" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>— no team —</SelectItem>
        {teams.map((t) => {
          const taken = t.claimed_by !== null && t.claimed_by !== self;
          return (
            <SelectItem key={t.team_id} value={String(t.team_id)} disabled={taken && !allowTaken}>
              {t.name}
              {taken ? ` (${t.claimed_by})` : ""}
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}

function ManageUsers({ myId }: { myId: string }) {
  const { data: users, isLoading } = useUsers(true);
  const teams = useLeagueTeams();
  const setUserTeam = useSetUserTeam();
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
        <CardDescription>Anyone with an account can see the whole draft board. Fix who manages which team here if an invite went to the wrong person.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Team</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Added</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {users?.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.username}</TableCell>
                  <TableCell className="text-muted-foreground">{u.email || "—"}</TableCell>
                  <TableCell>
                    <TeamPicker
                      value={u.team_id}
                      teams={teams.data ?? []}
                      disabled={setUserTeam.isPending}
                      allowTaken
                      self={u.username}
                      onChange={(id) =>
                        setUserTeam.mutate({ userId: u.id, teamId: id }, { onSuccess: () => toast.success(`Updated ${u.username}`), onError: (err) => toast.error(errorMessage(err)) })
                      }
                    />
                  </TableCell>
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
      {user.is_admin && <Invites />}
      {user.is_admin && <ManageUsers myId={user.id} />}
    </div>
  );
}

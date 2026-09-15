import { createContext, useContext } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost } from "./api";

export interface PublicUser {
  id: string;
  username: string;
  is_admin: boolean;
  created_at: string;
  /** The league team this person manages; set by the invite that created the account. */
  team_id: number | null;
  /** Where their invite went; shown to admins, never used to sign in. */
  email: string;
}

export interface AuthStatus {
  users_exist: boolean;
  allow_registration: boolean;
  /** The server can email invite links (SMTP is set up); otherwise admins copy them. */
  mail_configured: boolean;
}

export interface Credentials {
  username: string;
  password: string;
}

/** An emailed invite. There is deliberately no link here — it exists only in the email. */
export interface Invite {
  id: string;
  team_id: number;
  team_name: string;
  email: string;
  status: "pending" | "used" | "expired" | "revoked";
  created_at: string;
  expires_at: string;
  used_by: string | null;
  test: boolean;
  sent_at: string | null;
  /** The provider's reason when the email did not go out; empty when it did. */
  send_error: string;
  message_id: string;
}

export interface MailInfo {
  configured: boolean;
  provider: string;
  sender: string;
  reply_to: string;
  /** Resend's sandbox sender: it only delivers to the address the Resend account is registered under. */
  sandbox: boolean;
  /** What invite links start with; empty when APP_URL is missing on a split deploy. */
  link_base: string;
}

export interface InviteInfo {
  valid: boolean;
  reason: string;
  team_name: string;
  league_name: string;
  /** An admin's dry run: the page is identical, but submitting creates nothing. */
  test: boolean;
}

export interface JoinResult {
  user: PublicUser | null;
  test: boolean;
  message: string;
}

export interface LeagueTeam {
  team_id: number;
  name: string;
  owners: string[];
  claimed_by: string | null;
}

export const authKeys = {
  me: ["auth", "me"] as const,
  status: ["auth", "status"] as const,
  users: ["auth", "users"] as const,
  teams: ["auth", "teams"] as const,
  invites: ["auth", "invites"] as const,
  mail: ["auth", "mail"] as const,
  invite: (token: string) => ["auth", "invite", token] as const,
};

export interface AuthValue {
  user: PublicUser | null;
  loading: boolean;
}

export const AuthContext = createContext<AuthValue>({ user: null, loading: true });

export function useAuth(): AuthValue {
  return useContext(AuthContext);
}

/** Whether the sign-in page should also offer to create an account. */
export function useAuthStatus() {
  return useQuery({
    queryKey: authKeys.status,
    queryFn: () => apiGet<AuthStatus>("/auth/status"),
    staleTime: 60_000,
  });
}

function useCredentialMutation(path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => apiPost<PublicUser>(path, body),
    onSuccess: (user) => {
      qc.setQueryData(authKeys.me, user);
      qc.invalidateQueries({ queryKey: authKeys.status });
    },
  });
}

export function useLogin() {
  return useCredentialMutation("/auth/login");
}

export function useRegister() {
  return useCredentialMutation("/auth/register");
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<void>("/auth/logout"),
    onSuccess: () => {
      // Nothing cached under this session should survive into the next one.
      qc.setQueryData(authKeys.me, null);
      qc.removeQueries({
        predicate: ({ queryKey }) => queryKey[0] !== authKeys.me[0] || queryKey[1] !== authKeys.me[1],
      });
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) => apiPost<void>("/auth/password", body),
  });
}

export function useUsers(enabled: boolean) {
  return useQuery({
    queryKey: authKeys.users,
    queryFn: () => apiGet<PublicUser[]>("/auth/users"),
    enabled,
  });
}

export function useAddUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials & { is_admin: boolean }) => apiPost<PublicUser>("/auth/users", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.users }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => apiDelete<void>(`/auth/users/${userId}`),
    // Removing an account frees its team, so the invite screen changes too.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: authKeys.users });
      qc.invalidateQueries({ queryKey: authKeys.teams });
      qc.invalidateQueries({ queryKey: authKeys.invites });
    },
  });
}

/** Admin: the league's teams and who manages each one here. */
export function useLeagueTeams(enabled = true) {
  return useQuery({
    queryKey: authKeys.teams,
    queryFn: () => apiGet<LeagueTeam[]>("/auth/teams"),
    enabled,
    staleTime: 30_000,
  });
}

/** Admin: assign any member's team (takes it from whoever held it). */
export function useSetUserTeam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, teamId }: { userId: string; teamId: number | null }) => apiPost<PublicUser>(`/auth/users/${userId}/team`, { team_id: teamId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: authKeys.users });
      qc.invalidateQueries({ queryKey: authKeys.teams });
      qc.invalidateQueries({ queryKey: authKeys.me });
    },
  });
}

export function useMailInfo(enabled: boolean) {
  return useQuery({
    queryKey: authKeys.mail,
    queryFn: () => apiGet<MailInfo>("/auth/mail"),
    enabled,
    staleTime: 60_000,
  });
}

export function useInvites(enabled: boolean) {
  return useQuery({
    queryKey: authKeys.invites,
    queryFn: () => apiGet<Invite[]>("/auth/invites"),
    enabled,
  });
}

/** Emails a one-time link tied to the team. The server refuses without SMTP. */
export function useCreateInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { team_id: number; email: string }) => apiPost<Invite>("/auth/invites", body),
    // A 502 means the invite exists but the email failed; the list must show it so Resend is offered.
    onSettled: () => {
      qc.invalidateQueries({ queryKey: authKeys.invites });
      qc.invalidateQueries({ queryKey: authKeys.teams });
    },
  });
}

/** Emails the admin the exact invite a league-mate gets, for the admin's own team. Harmless to redeem. */
export function useTestInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (email: string) => apiPost<Invite>("/auth/invites/test", { email }),
    onSettled: () => qc.invalidateQueries({ queryKey: authKeys.invites }),
  });
}

export function useResendInvite() {
  return useMutation({
    mutationFn: (inviteId: string) => apiPost<Invite>(`/auth/invites/${inviteId}/resend`),
  });
}

export function useRevokeInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) => apiDelete<void>(`/auth/invites/${inviteId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.invites }),
  });
}

/** Unauthenticated: what an invite link is for, before the join form is shown. */
export function useInviteInfo(token: string | null) {
  return useQuery({
    queryKey: authKeys.invite(token ?? ""),
    queryFn: () => apiGet<InviteInfo>(`/auth/invite/${encodeURIComponent(token ?? "")}`),
    enabled: !!token,
    retry: false,
  });
}

export function useJoin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials & { token: string }) => apiPost<JoinResult>("/auth/join", body),
    onSuccess: (result) => {
      if (result.user) {
        qc.setQueryData(authKeys.me, result.user);
        qc.invalidateQueries({ queryKey: authKeys.status });
      }
    },
  });
}

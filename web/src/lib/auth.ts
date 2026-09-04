import { createContext, useContext } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost } from "./api";

export interface PublicUser {
  id: string;
  username: string;
  is_admin: boolean;
  created_at: string;
}

export interface AuthStatus {
  users_exist: boolean;
  allow_registration: boolean;
}

export interface Credentials {
  username: string;
  password: string;
}

export const authKeys = {
  me: ["auth", "me"] as const,
  status: ["auth", "status"] as const,
  users: ["auth", "users"] as const,
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
      qc.removeQueries();
      qc.setQueryData(authKeys.me, null);
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
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.users }),
  });
}

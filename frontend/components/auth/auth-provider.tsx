"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { authClient } from "@/lib/auth/client";
import type { OdinUser } from "@/lib/auth/types";

type AuthContextValue = {
  user: OdinUser | null;
  loading: boolean;
  refreshUser: () => Promise<OdinUser | null>;
  login: (
    identity: string,
    password: string,
    rememberMe: boolean,
  ) => Promise<OdinUser>;
  bootstrap: (
    username: string,
    email: string,
    password: string,
  ) => Promise<OdinUser>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  initialUser = null,
}: {
  children: ReactNode;
  initialUser?: OdinUser | null;
}) {
  const [user, setUser] = useState<OdinUser | null>(initialUser);
  const [loading, setLoading] = useState(false);

  const refreshUser = useCallback(async () => {
    setLoading(true);
    try {
      const nextUser = await authClient.me();
      setUser(nextUser);
      return nextUser;
    } catch {
      try {
        const refreshed = await authClient.refresh();
        setUser(refreshed.user);
        return refreshed.user;
      } catch {
        setUser(null);
        return null;
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(
    async (identity: string, password: string, rememberMe: boolean) => {
      const result = await authClient.login({
        username: identity,
        password,
      });
      setUser(result.user);
      return result.user;
    },
    [],
  );

  const bootstrap = useCallback(
    async (username: string, email: string, password: string) => {
      const result = await authClient.bootstrap({ username, email, password });
      setUser(result.user);
      return result.user;
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await authClient.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      refreshUser,
      login,
      bootstrap,
      logout,
    }),
    [user, loading, refreshUser, login, bootstrap, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}

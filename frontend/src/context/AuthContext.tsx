"use client";
import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { authApi } from "@/lib/api";

interface User {
  id: string;
  discord_id: string;
  discord_username: string;
  discord_avatar?: string;
  role: "user" | "admin";
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: () => Promise<void>;
  devLogin: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = (await authApi.me()) as User;
      setUser(me);
    } catch {
      // Attempt token refresh if access token expired
      try {
        await authApi.refresh();
        const me = (await authApi.me()) as User;
        setUser(me);
      } catch {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    const initAuth = async () => {
      try {
        const me = (await authApi.me()) as User;
        if (!ignore) setUser(me);
      } catch {
        try {
          await authApi.refresh();
          const me = (await authApi.me()) as User;
          if (!ignore) setUser(me);
        } catch {
          if (!ignore) setUser(null);
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    };
    void initAuth();
    return () => {
      ignore = true;
    };
  }, []);

  const login = async () => {
    const { url } = await authApi.getLoginUrl();
    window.location.assign(url);
  };

  const devLogin = async () => {
    setLoading(true);
    try {
      await authApi.devLogin();
      await refresh();
      window.location.assign("/user/dashboard");
    } catch (e) {
      console.error("Dev login failed", e);
      setLoading(false);
    }
  };

  const logout = async () => {
    await authApi.logout();
    setUser(null);
    window.location.assign("/");
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, devLogin, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

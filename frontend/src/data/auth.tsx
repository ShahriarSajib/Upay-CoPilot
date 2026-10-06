import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const TOKEN_KEY = "upay.copilot.token";

interface AuthState {
  token: string | null;
  userId: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, userId?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

async function request(path: string, body?: unknown, token?: string, method?: "GET" | "POST") {
  const response = await fetch(`${API_BASE}${path}`, {
    method: method ?? (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

export function apiBase() {
  return API_BASE;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [userId, setUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(() => Boolean(token));

  useEffect(() => {
    if (!token) {
      return;
    }
    request("/auth/me", undefined, token)
      .then((value) => setUserId(value.user_id ?? null))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  const authenticate = useCallback((value: { access_token: string; user_id?: string | null }) => {
    localStorage.setItem(TOKEN_KEY, value.access_token);
    setToken(value.access_token);
    setUserId(value.user_id ?? null);
    setLoading(false);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    authenticate(await request("/auth/login", { email, password }));
  }, [authenticate]);
  const signup = useCallback(async (email: string, password: string, selectedUserId?: string) => {
    authenticate(await request("/auth/signup", { email, password, user_id: selectedUserId || null }));
  }, [authenticate]);
  const logout = useCallback(async () => {
    // The route is a POST with no body, so the verb has to be explicit.
    if (token) await request("/auth/logout", undefined, token, "POST").catch(() => undefined);
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUserId(null);
  }, [token]);

  const value = useMemo(() => ({ token, userId, loading, login, signup, logout }), [token, userId, loading, login, signup, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

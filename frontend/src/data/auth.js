import { jsx as _jsx } from "react/jsx-runtime";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "upay.copilot.token";
const AuthContext = createContext(null);
async function request(path, body, token) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: body ? "POST" : "GET",
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
export function AuthProvider({ children }) {
    const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
    const [userId, setUserId] = useState(null);
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
    const authenticate = useCallback((value) => {
        localStorage.setItem(TOKEN_KEY, value.access_token);
        setToken(value.access_token);
        setUserId(value.user_id ?? null);
        setLoading(false);
    }, []);
    const login = useCallback(async (email, password) => {
        authenticate(await request("/auth/login", { email, password }));
    }, [authenticate]);
    const signup = useCallback(async (email, password, selectedUserId) => {
        authenticate(await request("/auth/signup", { email, password, user_id: selectedUserId || null }));
    }, [authenticate]);
    const logout = useCallback(async () => {
        if (token)
            await request("/auth/logout", undefined, token).catch(() => undefined);
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUserId(null);
    }, [token]);
    const value = useMemo(() => ({ token, userId, loading, login, signup, logout }), [token, userId, loading, login, signup, logout]);
    return _jsx(AuthContext.Provider, { value: value, children: children });
}
export function useAuth() {
    const value = useContext(AuthContext);
    if (!value)
        throw new Error("useAuth must be used inside <AuthProvider>");
    return value;
}

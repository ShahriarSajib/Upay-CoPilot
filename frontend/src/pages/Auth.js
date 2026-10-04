import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useAuth } from "@/data/auth";
export default function Auth() {
    const { login, signup } = useAuth();
    const [mode, setMode] = useState("login");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [userId, setUserId] = useState("");
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);
    async function submit(event) {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
            if (mode === "login")
                await login(email, password);
            else
                await signup(email, password, userId || undefined);
        }
        catch (reason) {
            setError(reason instanceof Error ? reason.message : "Unable to authenticate");
        }
        finally {
            setBusy(false);
        }
    }
    return (_jsx("main", { className: "grid min-h-screen place-items-center bg-ink-50 p-6", children: _jsxs("form", { onSubmit: submit, className: "card w-full max-w-md p-7", children: [_jsxs("div", { className: "mb-6", children: [_jsx("div", { className: "mb-3 grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-xl font-black text-white", children: "u" }), _jsx("h1", { className: "text-2xl font-bold text-ink-900", children: "upay Financial Life Copilot" }), _jsx("p", { className: "mt-1 text-sm text-ink-500", children: mode === "login" ? "Sign in to your financial workspace." : "Create your secure workspace." })] }), _jsxs("label", { className: "mb-4 block text-sm font-semibold text-ink-700", children: ["Email", _jsx("input", { required: true, type: "email", value: email, onChange: (e) => setEmail(e.target.value), className: "mt-1 w-full rounded-lg border border-ink-200 px-3 py-2" })] }), _jsxs("label", { className: "mb-4 block text-sm font-semibold text-ink-700", children: ["Password", _jsx("input", { required: true, minLength: 8, type: "password", value: password, onChange: (e) => setPassword(e.target.value), className: "mt-1 w-full rounded-lg border border-ink-200 px-3 py-2" })] }), mode === "signup" ? _jsxs("label", { className: "mb-4 block text-sm font-semibold text-ink-700", children: ["Test user ID (optional)", _jsx("input", { value: userId, onChange: (e) => setUserId(e.target.value.toUpperCase()), placeholder: "U00001", className: "mt-1 w-full rounded-lg border border-ink-200 px-3 py-2" })] }) : null, error ? _jsx("p", { className: "mb-4 rounded-lg bg-brand-50 p-3 text-sm text-brand-700", children: error }) : null, _jsx("button", { disabled: busy, className: "w-full rounded-lg bg-brand-600 px-4 py-2 font-bold text-white disabled:opacity-50", type: "submit", children: busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account" }), _jsx("button", { type: "button", className: "mt-4 w-full text-sm font-semibold text-brand-700", onClick: () => setMode(mode === "login" ? "signup" : "login"), children: mode === "login" ? "Need an account? Sign up" : "Already registered? Sign in" })] }) }));
}

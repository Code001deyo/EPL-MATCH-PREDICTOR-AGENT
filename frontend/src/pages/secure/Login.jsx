import { useState } from "react";
import axios from "axios";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import useAuth from "../../hooks/useAuth";
import { C, radius, space, type, semantic } from "../../theme";
import { API } from "../../config";

export default function AdminLogin() {
  const { login, admin, configured, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // No navigation on success. SecureModel renders the console once the session
  // is established, so the operator URL never enters browser history as a
  // separate entry and there is no second path to discover.
  if (loading) return <EmptyState kind="loading" title="Checking your session…" />;
  if (admin) return null;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      const status = err?.response?.status;
      // 429 is a distinct, actionable state — telling someone "incorrect
      // password" when they are actually rate-limited sends them to reset a
      // password that was never wrong.
      setError(
        status === 429 ? (err.response.data?.detail || "Too many attempts. Wait a moment and try again.")
        : status === 503 ? "Admin access is not configured on this server."
        : status === 401 ? "Incorrect username or password."
        : "Could not reach the server."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 380, margin: "8vh auto 0" }}>
      <div style={{ ...type.page, color: C.navy, marginBottom: 4 }}>Sign in</div>
      <div style={{ ...type.body, color: C.slate500, marginBottom: space.lg }}>
        Model operations.
      </div>

      <Card>
        {!configured ? (
          <EmptyState
            kind="not-measured"
            title="Admin is not configured on this server"
            detail="ADMIN_USERNAME, ADMIN_PASSWORD_HASH and SESSION_SECRET must be set in the deployment environment. Until then admin actions are disabled for everyone, which is the intended behaviour rather than an open door."
          />
        ) : (
          <form onSubmit={submit}>
            <Field label="Username" value={username} onChange={setUsername} autoComplete="username" autoFocus />
            <Field label="Password" value={password} onChange={setPassword} type="password" autoComplete="current-password" />

            {error && (
              <div style={{
                ...type.body, color: semantic.bad, background: semantic.badBg,
                border: `1px solid ${semantic.badBorder}`, borderRadius: radius.sm,
                padding: "8px 10px", marginBottom: space.md,
              }}>
                {error}
              </div>
            )}

            <Forgot username={username} />

            <button type="submit" disabled={busy || !username || !password} style={{
              width: "100%", padding: "10px 16px", borderRadius: radius.sm, border: "none",
              background: busy || !username || !password ? C.slate300 : C.navy,
              color: C.white, ...type.bodyStrong,
              cursor: busy || !username || !password ? "default" : "pointer",
            }}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}
      </Card>
    </div>
  );
}

function Field({ label, value, onChange, type: inputType = "text", ...rest }) {
  return (
    <div style={{ marginBottom: space.md }}>
      <label style={{ display: "block", ...type.label, color: C.slate600, marginBottom: 4 }}>{label}</label>
      <input
        type={inputType}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%", padding: "9px 11px", borderRadius: radius.sm,
          border: `1px solid ${C.slate200}`, fontSize: 14, boxSizing: "border-box",
        }}
        {...rest}
      />
    </div>
  );
}


/* Request a reset link.
 *
 * The confirmation is deliberately the same whether or not the account exists —
 * the server answers identically for both, and saying anything more specific here
 * would reintroduce the username oracle the endpoint was written to avoid.
 *
 * It also does not promise delivery. If the mail service is misconfigured the
 * server logs the link and the caller still sees this message, so the wording
 * says what was requested rather than what arrived. */
function Forgot({ username }) {
  const [state, setState] = useState("idle");   // idle | asking | sent

  const request = async () => {
    setState("asking");
    try {
      await axios.post(`${API}/auth/forgot`, { username });
    } catch {
      // Even a failure here must not distinguish cases; the operator is told the
      // same thing and the server log carries the detail.
    }
    setState("sent");
  };

  if (state === "sent") {
    return (
      <div style={{ ...type.micro, fontWeight: 400, color: C.slate500, marginBottom: space.md, lineHeight: 1.5 }}>
        If that account exists, a reset link has been sent to the address on file.
        The link works once and expires in 30 minutes.
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={request}
      disabled={!username || state === "asking"}
      title={username ? "" : "Enter your username first"}
      style={{
        background: "none", border: "none", padding: 0, marginBottom: space.md,
        ...type.micro, fontWeight: 400,
        color: username ? C.slate500 : C.slate300,
        cursor: username ? "pointer" : "default",
        textDecoration: "underline",
      }}
    >
      {state === "asking" ? "Sending…" : "Forgot password?"}
    </button>
  );
}

import { useState } from "react";
import axios from "axios";
import Card from "../../components/ui/Card";
import { C, radius, space, type, semantic } from "../../theme";
import { API } from "../../config";

const MIN_PASSWORD = 12;

/* Choose a new password from an emailed link.
 *
 * Reached as /secure-model?reset=<token>, so the operator area stays a single
 * unadvertised path with no second route to discover. The token is single-use and
 * expires in 30 minutes; the server says only "invalid or expired" for every
 * failure, because distinguishing them would help someone guessing tokens. */
export default function ResetPassword({ token, onDone }) {
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (next !== confirm) return setError("The passwords do not match.");
    if (next.length < MIN_PASSWORD) return setError(`Use at least ${MIN_PASSWORD} characters.`);
    setBusy(true); setError(null);
    try {
      await axios.post(`${API}/auth/reset`, { token, new_password: next });
      setDone(true);
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not reset the password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 380, margin: "8vh auto 0" }}>
      <div style={{ ...type.page, color: C.navy, marginBottom: 4 }}>Choose a new password</div>
      <Card>
        {done ? (
          <>
            <Note tone="good">Password updated. Every existing session has been signed out.</Note>
            <button onClick={onDone} style={btn(false)}>Go to sign in</button>
          </>
        ) : (
          <form onSubmit={submit}>
            <Field label="New password" value={next} onChange={setNext} hint={`At least ${MIN_PASSWORD} characters.`} />
            <Field label="Confirm password" value={confirm} onChange={setConfirm} />
            {error && <Note tone="bad">{error}</Note>}
            <button type="submit" disabled={busy || !next || !confirm} style={btn(busy || !next || !confirm)}>
              {busy ? "Saving…" : "Set new password"}
            </button>
          </form>
        )}
      </Card>
    </div>
  );
}

function Field({ label, value, onChange, hint }) {
  return (
    <div style={{ marginBottom: space.md }}>
      <label style={{ display: "block", ...type.label, color: C.slate600, marginBottom: 4 }}>{label}</label>
      <input type="password" value={value} autoComplete="new-password"
        onChange={(e) => onChange(e.target.value)} style={{
          width: "100%", padding: "9px 11px", borderRadius: radius.sm,
          border: `1px solid ${C.slate200}`, fontSize: 14, boxSizing: "border-box",
        }} />
      {hint && <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: 3 }}>{hint}</div>}
    </div>
  );
}

function Note({ tone, children }) {
  const t = tone === "good"
    ? { fg: semantic.good, bg: semantic.goodBg, border: semantic.goodBorder }
    : { fg: semantic.bad, bg: semantic.badBg, border: semantic.badBorder };
  return (
    <div style={{
      marginBottom: space.md, padding: "8px 10px", borderRadius: radius.sm,
      background: t.bg, border: `1px solid ${t.border}`, color: t.fg, ...type.body,
    }}>{children}</div>
  );
}

function btn(off) {
  return {
    width: "100%", padding: "10px 16px", borderRadius: radius.sm, border: "none",
    background: off ? C.slate300 : C.navy, color: C.white, ...type.bodyStrong,
    cursor: off ? "default" : "pointer",
  };
}

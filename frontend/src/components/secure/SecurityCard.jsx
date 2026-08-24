import { useState } from "react";
import axios from "axios";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import useAuth from "../../hooks/useAuth";
import { C, radius, space, type, semantic } from "../../theme";
import { API } from "../../config";

const MIN_PASSWORD = 12;

/* Change the operator's own credentials.
 *
 * Both forms ask for the current password even though the caller is already
 * signed in. That is not friction for its own sake: a session alone must not be
 * enough to change the credential, or anyone holding a borrowed cookie could lock
 * the real operator out of their own account. The server enforces it too — this
 * form is a convenience, not the control. */
export default function SecurityCard() {
  const { refresh } = useAuth();
  return (
    <Card>
      <SectionTitle sub="Changing either signs out every other session. This one stays signed in.">
        Security
      </SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: space.xl }}>
        <ChangePassword onDone={refresh} />
        <ChangeUsername onDone={refresh} />
      </div>
    </Card>
  );
}

function ChangePassword({ onDone }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const form = useSubmit(async () => {
    if (next !== confirm) throw new Error("The new passwords do not match.");
    if (next.length < MIN_PASSWORD) throw new Error(`Use at least ${MIN_PASSWORD} characters.`);
    await axios.post(`${API}/auth/change-password`, { current_password: current, new_password: next });
    setCurrent(""); setNext(""); setConfirm("");
    return "Password changed. Other sessions have been signed out.";
  }, onDone);

  return (
    <form onSubmit={form.submit}>
      <Legend>Change password</Legend>
      <Field label="Current password" type="password" value={current} onChange={setCurrent} autoComplete="current-password" />
      <Field label="New password" type="password" value={next} onChange={setNext} autoComplete="new-password"
        hint={`At least ${MIN_PASSWORD} characters.`} />
      <Field label="Confirm new password" type="password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
      <Submit busy={form.busy} disabled={!current || !next || !confirm}>Change password</Submit>
      <Feedback {...form} />
    </form>
  );
}

function ChangeUsername({ onDone }) {
  const { username } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const form = useSubmit(async () => {
    await axios.post(`${API}/auth/change-username`, { current_password: current, new_username: next });
    setCurrent(""); setNext("");
    return "Username changed. Sign in with it next time.";
  }, onDone);

  return (
    <form onSubmit={form.submit}>
      <Legend>Change username</Legend>
      <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginBottom: space.sm }}>
        Currently <strong style={{ color: C.slate600 }}>{username}</strong>
      </div>
      <Field label="New username" value={next} onChange={setNext} autoComplete="username" />
      <Field label="Current password" type="password" value={current} onChange={setCurrent} autoComplete="current-password" />
      <Submit busy={form.busy} disabled={!current || next.length < 3}>Change username</Submit>
      <Feedback {...form} />
    </form>
  );
}

/* Shared submit handling: one busy flag, one error, one success line. */
function useSubmit(action, onDone) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError(null); setDone(null);
    try {
      setDone(await action());
      if (onDone) await onDone();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "That did not work.");
    } finally {
      setBusy(false);
    }
  };
  return { submit, busy, error, done };
}

function Legend({ children }) {
  return <div style={{ ...type.bodyStrong, color: C.slate700, marginBottom: space.sm }}>{children}</div>;
}

function Field({ label, value, onChange, type: inputType = "text", hint, ...rest }) {
  return (
    <div style={{ marginBottom: space.sm }}>
      <label style={{ display: "block", ...type.label, color: C.slate600, marginBottom: 3 }}>{label}</label>
      <input type={inputType} value={value} onChange={(e) => onChange(e.target.value)} style={{
        width: "100%", padding: "8px 10px", borderRadius: radius.sm,
        border: `1px solid ${C.slate200}`, fontSize: 13, boxSizing: "border-box",
      }} {...rest} />
      {hint && <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: 3 }}>{hint}</div>}
    </div>
  );
}

function Submit({ busy, disabled, children }) {
  const off = busy || disabled;
  return (
    <button type="submit" disabled={off} style={{
      padding: "8px 14px", borderRadius: radius.sm, border: "none",
      background: off ? C.slate300 : C.navy, color: C.white,
      ...type.label, cursor: off ? "default" : "pointer", marginTop: 4,
    }}>
      {busy ? "Working…" : children}
    </button>
  );
}

function Feedback({ error, done }) {
  if (!error && !done) return null;
  const t = error
    ? { fg: semantic.bad, bg: semantic.badBg, border: semantic.badBorder }
    : { fg: semantic.good, bg: semantic.goodBg, border: semantic.goodBorder };
  return (
    <div style={{
      marginTop: space.sm, padding: "7px 10px", borderRadius: radius.sm,
      background: t.bg, border: `1px solid ${t.border}`, color: t.fg, ...type.micro, fontWeight: 400,
    }}>
      {error || done}
    </div>
  );
}

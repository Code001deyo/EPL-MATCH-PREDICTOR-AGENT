import { C, radius } from "../../theme";

// Shared form select. Extracted from Predict.jsx when UpcomingSelector moved
// out, so both halves of that page keep using the same control.
export default function Select({ label, value, onChange, children, disabled }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: C.slate500, marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</label>
      <select value={value} onChange={onChange} disabled={disabled}
        style={{ width: "100%", padding: "9px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 14, background: C.white, color: C.slate700 }}>
        {children}
      </select>
    </div>
  );
}

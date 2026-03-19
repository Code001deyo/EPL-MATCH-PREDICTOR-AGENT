import { C, shadow, radius } from "../../theme";

export default function KpiCard({ icon, label, value, sub, color = C.blue }) {
  return (
    <div style={{ background: C.white, borderRadius: radius.lg, padding: "20px 24px", boxShadow: shadow.card, flex: 1, minWidth: 160 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 22 }}>{icon}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: C.slate500, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>
      </div>
      <div style={{ fontSize: 32, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: C.slate400, marginTop: 6 }}>{sub}</div>}
    </div>
  );
}

import { C } from "../../theme";

const VARIANTS = {
  exact:   { bg: "#d1fae5", color: C.emerald, label: "✅ Exact Score" },
  result:  { bg: "#fef3c7", color: "#92400e", label: "🟡 Correct Result" },
  wrong:   { bg: "#fee2e2", color: C.rose,    label: "❌ Wrong" },
  pending: { bg: C.slate100, color: C.slate500, label: "⏳ Pending" },
};

export function resultVariant(predicted, actual) {
  if (!actual || actual === "null-null") return "pending";
  const [ph, pa] = predicted.split("-").map(Number);
  const [ah, aa] = actual.split("-").map(Number);
  if (ph === ah && pa === aa) return "exact";
  const pr = ph > pa ? "H" : ph === pa ? "D" : "A";
  const ar = ah > aa ? "H" : ah === aa ? "D" : "A";
  return pr === ar ? "result" : "wrong";
}

export default function Badge({ variant = "pending", small }) {
  const v = VARIANTS[variant] || VARIANTS.pending;
  return (
    <span style={{
      background: v.bg, color: v.color,
      padding: small ? "2px 8px" : "4px 12px",
      borderRadius: 20, fontSize: small ? 11 : 12,
      fontWeight: 600, whiteSpace: "nowrap",
    }}>
      {v.label}
    </span>
  );
}

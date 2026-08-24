import { C, shadow, radius } from "../../theme";

// Shared card shell. Previously redefined per-page (Dashboard, Analytics,
// Teams, History, ModelPage, Predict all had their own copy).
export default function Card({ children, style, muted }) {
  return (
    <div
      style={{
        background: muted ? C.slate50 : C.white,
        borderRadius: radius.lg,
        boxShadow: muted ? "none" : shadow.card,
        border: muted ? `1px solid ${C.slate200}` : "none",
        padding: 24,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

import { C, semantic, radius } from "../../theme";

// The one honest way to say "there is nothing to show yet." Never render a
// 0%, a blank chart axis, or a placeholder number in its place — this is the
// component that renders instead.
//
// kind: "loading" | "not-measured" | "error"
export default function EmptyState({ kind = "not-measured", title, detail, action }) {
  const palette = {
    loading: { color: C.slate400, bg: C.slate50, border: C.slate200 },
    "not-measured": { color: semantic.neutral, bg: semantic.neutralBg, border: semantic.neutralBorder },
    error: { color: semantic.bad, bg: semantic.badBg, border: semantic.badBorder },
  }[kind];

  return (
    <div
      style={{
        textAlign: "center",
        padding: "36px 20px",
        borderRadius: radius.md,
        background: palette.bg,
        border: `1px dashed ${palette.border}`,
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 700, color: palette.color }}>
        {title || (kind === "loading" ? "Loading…" : kind === "error" ? "Could not load" : "Not yet measured")}
      </div>
      {detail && <div style={{ fontSize: 12, color: C.slate400, marginTop: 6, lineHeight: 1.6 }}>{detail}</div>}
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
    </div>
  );
}

import { C, type } from "../../theme";

// Shared section heading. `level="primary"` is for the one or two things on
// a page that matter most; default is the ordinary section weight. Previously
// every section title on every page rendered at the same 15px/700, so the
// most important number on the dashboard and the least important looked
// identical.
export default function SectionTitle({ children, level = "default", sub }) {
  const style = level === "primary" ? type.title : type.section;
  return (
    <div style={{ marginBottom: sub ? 4 : 16 }}>
      <div style={{ ...style, color: C.slate800 }}>{children}</div>
      {sub && <div style={{ fontSize: 12, color: C.slate400, marginTop: 2, marginBottom: 12 }}>{sub}</div>}
    </div>
  );
}

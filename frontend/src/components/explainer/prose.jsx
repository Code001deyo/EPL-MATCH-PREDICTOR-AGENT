import { C, radius, space, type } from "../../theme";

/* Three small typographic pieces the explainer needs and the rest of the app
 * does not.
 *
 * Every other page in this app is a dashboard: short labels, numbers, tables.
 * This one is the only page with running prose, which needs things none of the
 * existing ui/ components provide — a measure that keeps lines near 65
 * characters, a pulled-out figure, and an aside that carries a caveat without
 * looking like a warning. They live here rather than in ui/ because a component
 * used on exactly one page is not yet a shared treatment, and promoting it into
 * the shared set would imply the dashboards should start growing paragraphs.
 */

// Running text. `maxWidth` is the whole point: at the page's 820px the same text
// would run to ~110 characters a line, which is roughly twice a comfortable
// measure and is what makes long text on dashboards unreadable.
export function P({ children }) {
  return (
    <p style={{
      ...type.body,
      fontSize: 14,
      color: C.slate600,
      maxWidth: "66ch",
      margin: `0 0 ${space.md}px`,
    }}>
      {children}
    </p>
  );
}

// A single figure lifted out of the prose, for the one number in a section that
// the reader should leave with.
export function Pull({ value, unit, children }) {
  return (
    <div style={{
      display: "flex", gap: space.lg, alignItems: "center", flexWrap: "wrap",
      borderTop: `2px solid ${C.slate800}`,
      borderBottom: `1px solid ${C.slate200}`,
      padding: `${space.lg}px 0`,
      margin: `${space.xl}px 0`,
    }}>
      <div style={{
        ...type.statLg, color: C.navy, flex: "none",
        fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em",
      }}>
        {value}
        {unit && <span style={{ fontSize: 18, fontWeight: 600 }}>{unit}</span>}
      </div>
      <div style={{ ...type.body, fontSize: 14, color: C.slate600, flex: "1 1 18rem", minWidth: 0 }}>
        {children}
      </div>
    </div>
  );
}

// A caveat or a reframing. Deliberately not semantic.warn — nothing here is
// wrong, and tinting it amber would tell the reader to worry about a passage
// whose job is to reassure them.
export function Aside({ label, children }) {
  return (
    <div style={{
      background: C.slate50,
      border: `1px solid ${C.slate200}`,
      borderLeft: `3px solid ${C.navy}`,
      borderRadius: `0 ${radius.md}px ${radius.md}px 0`,
      padding: `${space.lg}px ${space.lg}px`,
      margin: `${space.lg}px 0`,
      maxWidth: "70ch",
    }}>
      <div style={{
        ...type.micro, color: C.slate400, marginBottom: 6,
        textTransform: "uppercase", letterSpacing: "0.1em",
      }}>
        {label}
      </div>
      <div style={{ ...type.body, fontSize: 14, color: C.slate700 }}>{children}</div>
    </div>
  );
}

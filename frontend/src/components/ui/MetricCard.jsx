import { C, semantic, radius, shadow, type } from "../../theme";
import InfoTip from "./InfoTip";

/* One card for "a number with a label", used everywhere.
 *
 * There were three visual languages for this: KpiCard on Analytics and ModelPage,
 * Card + Stat on the Dashboard, and bare divs in the head-to-head block. Same idea,
 * three paddings, three type scales, three colour rules — the three pages read as
 * three products.
 *
 * Compact by design: the dashboard's KPI strip has to fit six of these in one row
 * above the fold, so the value is 26px rather than the old 32-34px and the padding
 * is tighter. `size="lg"` restores the larger treatment where a page has room.
 *
 * `delta` is the piece that keeps the dashboard honest after the prose moved into
 * tooltips: it carries the comparison — "+2.6 vs baseline" — inline, so a reader
 * who never hovers still sees that 46% is measured against something. */
export default function MetricCard({
  label, value, sub, delta, info, size = "md", accent = C.navy, muted = false,
}) {
  const big = size === "lg";
  return (
    <div style={{
      background: muted ? C.slate50 : C.white,
      border: muted ? `1px solid ${C.slate200}` : "none",
      borderRadius: radius.lg,
      boxShadow: muted ? "none" : shadow.card,
      padding: big ? "18px 22px" : "14px 16px",
      minWidth: 0,          // lets the card shrink inside a grid track
      display: "flex", flexDirection: "column", gap: 4,
    }}>
      <div style={{ display: "flex", alignItems: "center", minHeight: 16 }}>
        <span style={{
          ...type.micro, color: C.slate500,
          textTransform: "uppercase", letterSpacing: "0.05em",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {label}
        </span>
        {info && <InfoTip label={`About ${label}`}>{info}</InfoTip>}
      </div>

      <div style={{
        fontSize: big ? 34 : 26, fontWeight: 800, lineHeight: 1.05,
        color: accent, letterSpacing: "-0.02em",
      }}>
        {value}
      </div>

      {(delta || sub) && (
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
          {delta && <DeltaChip {...delta} />}
          {sub && <span style={{ ...type.micro, fontWeight: 400, color: C.slate400 }}>{sub}</span>}
        </div>
      )}
    </div>
  );
}

/* A signed comparison, coloured by whether it is good — not by which series it
 * belongs to. `marginalAt` exists because a model beating its baseline by 2.6
 * points should not be dressed in the same confident green as one beating it by
 * 12: below the threshold the chip goes neutral grey regardless of sign. */
function DeltaChip({ value, suffix = "pts", marginalAt = 3, invert = false }) {
  if (!Number.isFinite(value)) return null;
  const good = invert ? value < 0 : value > 0;
  const marginal = Math.abs(value) < marginalAt;
  const tone = marginal
    ? { fg: semantic.neutral, bg: semantic.neutralBg }
    : good
    ? { fg: semantic.good, bg: semantic.goodBg }
    : { fg: semantic.bad, bg: semantic.badBg };

  return (
    <span style={{
      ...type.micro, color: tone.fg, background: tone.bg,
      padding: "1px 6px", borderRadius: radius.sm, whiteSpace: "nowrap",
    }}>
      {value > 0 ? "+" : ""}{value.toFixed(1)} {suffix}
    </span>
  );
}

import { C, semantic, type } from "../../theme";

// A judged number: a value plus, optionally, a delta against a baseline.
// The delta's colour and its bar length both come from magnitude, not from
// whether the number is merely positive — a +1.3pt edge renders as visibly
// marginal, not as a green tick. Deltas near zero are always "neutral"
// regardless of sign, because a 0.3pt edge is not a win, it is noise.
//
// size: "lg" (headline) | "md" (default)
export default function Stat({ label, value, unit = "", detail, delta, size = "md" }) {
  const valueStyle = size === "lg" ? type.statLg : type.stat;

  return (
    <div>
      <div style={{ ...type.label, color: C.slate500, textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 6 }}>
        <span style={{ ...valueStyle, color: C.slate800 }}>{value}</span>
        {unit && <span style={{ fontSize: 15, color: C.slate400, fontWeight: 600 }}>{unit}</span>}
      </div>
      {detail && <div style={{ fontSize: 12, color: C.slate400, marginTop: 4 }}>{detail}</div>}
      {delta && <DeltaBar {...delta} />}
    </div>
  );
}

// magnitude: how big the edge is, in the metric's own units (points, log-loss
// units, etc). marginalAt: the magnitude below which this reads as noise, not
// a result — the bar and colour both collapse to neutral under that line.
function DeltaBar({ label, magnitude, marginalAt = 2, scaleMax = 10, positiveIsGood = true }) {
  const abs = Math.abs(magnitude);
  const isMarginal = abs < marginalAt;
  const isGood = positiveIsGood ? magnitude > 0 : magnitude < 0;

  const tone = isMarginal ? semantic.neutral : isGood ? semantic.good : semantic.bad;
  const pct = Math.min(100, (abs / scaleMax) * 100);

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: C.slate500, marginBottom: 4 }}>
        <span>{label}</span>
        <span style={{ color: tone, fontWeight: 700 }}>
          {magnitude > 0 ? "+" : ""}{magnitude.toFixed(1)}
          {isMarginal && " · marginal"}
        </span>
      </div>
      <div style={{ background: C.slate100, borderRadius: 4, height: 6, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, background: tone, height: "100%", minWidth: pct > 0 ? 4 : 0, transition: "width 0.4s" }} />
      </div>
    </div>
  );
}

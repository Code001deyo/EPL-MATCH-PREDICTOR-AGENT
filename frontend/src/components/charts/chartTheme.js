/* Shared chart styling and series colours.
 *
 * Before this module, every chart in the app re-declared its own axis ticks,
 * grid stroke and series colours inline, and they had drifted apart: Analytics
 * drew its lines in PL green and red, ModelPage drew its bars in two greys, and
 * the dashboard had no charts at all. Same data language, three different looks.
 *
 * The token rule from theme.js still applies and is the reason this file exists
 * rather than a single flat palette: `series` below draws from the EPL BRAND
 * tokens, because a chart line is decoration — it identifies a series, it does
 * not judge it. `semantic` (good/warn/bad) stays reserved for saying a number is
 * good or bad. A model's accuracy line must not be green because the accuracy is
 * good; it is green because it is the model's line.
 */
import { C, semantic } from "../../theme";

// Series colours, in the order a chart should reach for them.
export const series = {
  primary: C.navy,        // PL purple — the subject of the chart (the model)
  accent: C.blue,         // PL green — the comparison the subject is measured against
  muted: C.slate400,      // supporting series that must not compete for attention
  baseline: C.slate300,   // reference lines: the diagonal, always-home, zero
};

// A baseline is not a rival series. Dashed and grey so the eye reads it as the
// floor being cleared rather than as a second thing to track.
export const baselineLine = {
  stroke: series.baseline,
  strokeWidth: 2,
  strokeDasharray: "5 4",
  dot: false,
};

export const axis = {
  tick: { fontSize: 11, fill: C.slate500 },
  axisLine: { stroke: C.slate200 },
  tickLine: false,
};

export const grid = {
  strokeDasharray: "3 3",
  stroke: C.slate100,
  vertical: false,
};

export const tooltipStyle = {
  contentStyle: {
    borderRadius: 8,
    border: `1px solid ${C.slate200}`,
    fontSize: 12,
    boxShadow: "0 4px 16px rgba(0,0,0,0.10)",
  },
  labelStyle: { color: C.slate600, fontWeight: 700, marginBottom: 4 },
};

export const legendStyle = { fontSize: 12, paddingTop: 8 };

export const pct = (v) => `${Math.round(v)}%`;

/**
 * Trailing rolling mean over `window` points.
 *
 * Needed because the backtest series is per matchweek and a Premier League
 * matchweek is only 10 matches: a single week swings between 20% and 80% correct
 * on sample size alone. Plotted raw it reads as noise, and a reader would draw
 * conclusions from spikes that are not there.
 *
 * Trailing, not centred, so no point is computed from weeks that had not happened
 * yet — the same point-in-time discipline the features follow. The first
 * `window - 1` points average over what exists so far rather than being dropped,
 * so the line starts where the data starts; they are correspondingly noisier,
 * which is honest for an early-season average.
 *
 * The raw value is preserved on each point so the tooltip can show what actually
 * happened that week alongside the smoothed trend.
 */
export function rollingMean(rows, keys, window = 5) {
  return rows.map((row, i) => {
    const from = Math.max(0, i - window + 1);
    const slice = rows.slice(from, i + 1);
    const out = { ...row, _window: slice.length };
    for (const key of keys) {
      const vals = slice.map((r) => r[key]).filter((v) => Number.isFinite(v));
      // Missing means missing: an all-NaN window yields no smoothed point
      // rather than a fabricated zero.
      out[`${key}_avg`] = vals.length
        ? vals.reduce((a, b) => a + b, 0) / vals.length
        : null;
    }
    return out;
  });
}

// Colour a delta by whether it is good, not by which series it belongs to.
// This is the one place semantic tokens are correct inside a chart surround.
export const deltaColor = (v) =>
  !Number.isFinite(v) ? semantic.neutral : v > 0 ? semantic.good : v < 0 ? semantic.bad : semantic.neutral;

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
//
// Both are brand colours — PL purple and PL green — and neither is grey. Grey
// series on a white card wash out: at 1-2px a #cbd5e1 line is barely above the
// gridlines, so the baseline the model is being judged against was the hardest
// thing on the chart to see. The comparison has to be legible for the comparison
// to mean anything.
//
// The green used is blueDark (#00b368) rather than the signature #00ff85: the
// bright green is a fill and background colour, and as a 2px line on white it has
// too little contrast to read.
export const series = {
  primary: C.navy,        // PL purple — the subject of the chart (the model)
  accent: C.blue,         // PL green — a second series of equal standing
  muted: C.blueDark,      // supporting series that must not compete for attention
  baseline: C.blueDark,   // reference lines: the diagonal, always-home, zero
};

// A baseline is not a rival series, so it stays dashed — the dash pattern, not a
// washed-out colour, is what says "this is the floor being cleared".
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

// Gridlines are the one place a pale neutral is right: they are furniture behind
// the data, not a series competing with it.
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

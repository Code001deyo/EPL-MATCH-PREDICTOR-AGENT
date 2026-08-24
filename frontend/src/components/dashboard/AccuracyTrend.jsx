import { useMemo } from "react";
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ReferenceLine,
} from "recharts";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import EmptyState from "../ui/EmptyState";
import InfoTip from "../ui/InfoTip";
import { C, type, space } from "../../theme";
import { series, baselineLine, axis, grid, tooltipStyle, legendStyle, pct, rollingMean, deltaColor } from "../charts/chartTheme";
import useBacktest from "../../hooks/useBacktest";

const WINDOW = 5;

/* The dashboard's headline chart.
 *
 * GET /model/backtest already returns `by_matchweek` — 114 scored matchweeks
 * across three seasons, each with the model's correct-result % and the
 * always-home baseline for the same fixtures. Nothing in the app rendered it.
 * A dashboard that leads with a single accuracy number cannot show whether that
 * number is holding, drifting or was carried by one good season.
 *
 * The model line is plotted against the baseline so the edge reads as a gap
 * rather than as an assertion. If the gap closes, the chart says so. */
export default function AccuracyTrend() {
  const { status, data: payload } = useBacktest();

  const rows = payload?.by_matchweek || [];
  // Smoothing 114 points on every render would be wasted work; it only changes
  // when the payload does.
  const data = useMemo(() => prepare(rows), [rows]);
  const seasons = useMemo(() => seasonBoundaries(rows), [rows]);
  const headline = payload?.headline || null;

  // A backtest that ran but scored nothing is "not measured", not "ready".
  const state = status === "ready" && rows.length === 0 ? "not-measured" : status;

  return (
    <Card>
      {/* The explanation moved into the ⓘ. It is the same text; it simply is not
          two lines of paragraph above a chart on a dashboard any more. */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <span style={{ ...type.section, color: C.slate800 }}>Accuracy over time</span>
        <InfoTip label="About the accuracy trend">
          Correct-result rate per matchweek across the backtested seasons, smoothed over a
          trailing {WINDOW}-week window — a single matchweek is only 10 matches and swings
          wildly on sample size alone. Trailing rather than centred, so no point is computed
          from weeks that had not happened yet. The dashed line is the always-home baseline
          over the same fixtures; hover any point for that week's raw figure.
        </InfoTip>
      </div>

      {state === "loading" && <EmptyState kind="loading" />}
      {state === "error" && <EmptyState kind="error" title="Could not load the backtest" />}
      {state === "not-measured" && (
        <EmptyState
          kind="not-measured"
          title="No backtest has been run"
          detail="This trend is computed from the walk-forward backtest. Run one from the calibration panel below to populate it."
        />
      )}

      {state === "ready" && (
        <>
          <ResponsiveContainer width="100%" height={230}>
            <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -12 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="label" {...axis} interval="preserveStartEnd" minTickGap={28} />
              <YAxis domain={[0, 100]} tickFormatter={pct} {...axis} />
              <Tooltip {...tooltipStyle} content={<TrendTooltip />} />
              <Legend wrapperStyle={legendStyle} />

              {/* Season boundaries: accuracy is not comparable straight across
                  them — each new season refits on a squad the model has not seen. */}
              {seasons.map((s) => (
                <ReferenceLine key={s.label} x={s.label} stroke={C.blueDark} strokeOpacity={0.45}
                  strokeDasharray="2 4" label={{ value: s.season, position: "insideTopLeft", fontSize: 10, fill: C.blueDark }} />
              ))}

              <Line type="monotone" dataKey="correct_result_pct_avg" name="Model"
                stroke={series.primary} strokeWidth={2.5} dot={false} connectNulls={false} />
              <Line type="monotone" dataKey="always_home_pct_avg" name="Always home"
                {...baselineLine} legendType="plainline" />
            </ComposedChart>
          </ResponsiveContainer>
        </>
      )}
    </Card>
  );
}

/* Two baselines, not one.
 *
 * A bare "53.6% correct" is uninterpretable. It reads as a failure to anyone who
 * assumes a coin-flip floor, and as a triumph to anyone who does not know what is
 * achievable. Both readings are wrong, and the difference between them is the
 * whole question of whether this model can be trusted.
 *
 * So the figure is shown between the two numbers that bound it: the naive
 * baseline it has to beat, and the bookmakers' closing line on the same fixtures,
 * which is as close to a ceiling as this problem has. Measured over 7,980
 * Premier League matches the market gets ~54.6% and always-picking-home ~44.7%.
 * The entire space a model can compete in is about ten points wide.
 *
 * RPS is shown alongside because accuracy is not a proper scoring rule - it
 * rewards overconfidence and ignores everything the model said about the other
 * two outcomes. RPS is what the model is actually tuned against.
 */
function Headline({ headline }) {
  const edge = headline.correct_result_pct - headline.always_home_pct;
  const market = headline.market_correct_pct;
  const hasMarket = Number.isFinite(market);
  const gap = hasMarket ? headline.correct_result_pct - market : null;

  return (
    <div style={{ display: "flex", gap: space.xxl, flexWrap: "wrap", marginBottom: space.lg }}>
      <Figure label="Always home" value={`${headline.always_home_pct}%`} color={C.slate500} />
      <Figure label="Correct result" value={`${headline.correct_result_pct}%`} color={series.primary} />
      {hasMarket && (
        <Figure label="Bookmakers, same fixtures" value={`${market}%`} color={C.slate500} />
      )}
      <Figure label="Edge over always-home" value={`${edge > 0 ? "+" : ""}${edge.toFixed(1)} pts`} color={deltaColor(edge)} />
      {hasMarket && (
        // Signed against the market: negative means the bookmakers did better,
        // which is the expected and honest case rather than something to hide.
        <Figure label="vs bookmakers" value={`${gap > 0 ? "+" : ""}${gap.toFixed(1)} pts`} color={deltaColor(gap)} />
      )}
      {Number.isFinite(headline.rps) && (
        <Figure label="RPS (lower is better)" value={headline.rps.toFixed(4)} color={series.primary} />
      )}
      <Figure label="Matches scored" value={headline.matches} color={C.slate500} />
    </div>
  );
}

function Figure({ label, value, color }) {
  return (
    <div>
      <div style={{ ...type.label, color: C.slate500 }}>{label}</div>
      <div style={{ ...type.stat, fontSize: 26, color, marginTop: 4 }}>{value}</div>
    </div>
  );
}

// Shows the smoothed value and the raw week behind it, so the reader can see
// what the smoothing is hiding rather than only its output.
function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const line = (name, v) => (Number.isFinite(v) ? `${name}: ${v.toFixed(1)}%` : null);
  return (
    <div style={{ ...tooltipStyle.contentStyle, background: C.white, padding: "8px 10px" }}>
      <div style={{ ...tooltipStyle.labelStyle }}>{row.season} · MW{row.matchweek}</div>
      <div style={{ color: series.primary }}>{line(`Model (${row._window}-wk avg)`, row.correct_result_pct_avg)}</div>
      <div style={{ color: C.slate500 }}>{line(`Always home (${row._window}-wk avg)`, row.always_home_pct_avg)}</div>
      <div style={{ color: C.slate400, marginTop: 4, fontSize: 11 }}>
        This week raw: {row.correct_result_pct}% over {row.matches} matches
      </div>
    </div>
  );
}

function prepare(rows) {
  const withLabels = rows.map((r) => ({ ...r, label: `${r.season} MW${r.matchweek}` }));
  return rollingMean(withLabels, ["correct_result_pct", "always_home_pct"], WINDOW);
}

// First matchweek of each season after the first — the ones worth marking.
function seasonBoundaries(rows) {
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    if (seen.has(r.season)) continue;
    seen.add(r.season);
    if (seen.size > 1) out.push({ season: r.season, label: `${r.season} MW${r.matchweek}` });
  }
  return out;
}

import { useMemo } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, LabelList } from "recharts";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import EmptyState from "../ui/EmptyState";
import InfoTip from "../ui/InfoTip";
import { C, type, space } from "../../theme";
import { series, axis, grid, tooltipStyle, legendStyle, pct, deltaColor } from "../charts/chartTheme";
import useBacktest from "../../hooks/useBacktest";

/* Per-season backtest results, model against the always-home baseline.
 *
 * The headline "53.3% correct" is an average over three seasons that were not
 * equally kind: the per-season spread is real and a single blended figure hides
 * it. `by_season` is already returned by GET /model/backtest and, like
 * by_matchweek, was rendered nowhere. */
export default function SeasonComparison() {
  const { status, data: payload } = useBacktest();

  const rows = useMemo(
    () => (payload?.by_season || []).map((s) => ({ ...s, edge: s.correct_result_pct - s.always_home_pct })),
    [payload]
  );
  const state = status === "ready" && rows.length === 0 ? "not-measured" : status;

  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <span style={{ ...type.section, color: C.slate800 }}>Season by season</span>
        <InfoTip label="About the season comparison">
          Each backtested season scored on its own, against the always-home baseline for the
          same fixtures. The headline backtest figure is an average over these seasons, and
          they are not alike — the edge has narrowed each year.
        </InfoTip>
      </div>

      {state === "loading" && <EmptyState kind="loading" />}
      {state === "error" && <EmptyState kind="error" title="Could not load the backtest" />}
      {state === "not-measured" && (
        <EmptyState kind="not-measured" title="No backtest has been run"
          detail="Run one from the calibration panel to populate this." />
      )}

      {state === "ready" && (
        <>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={rows} margin={{ top: 16, right: 8, bottom: 0, left: -16 }} barGap={4}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="season" {...axis} />
              <YAxis domain={[0, 100]} tickFormatter={pct} {...axis} />
              <Tooltip {...tooltipStyle}
                formatter={(v, n) => [`${v}%`, n]}
                labelFormatter={(l) => `Season ${l}`} />
              <Legend wrapperStyle={legendStyle} />
              <Bar dataKey="correct_result_pct" name="Model" fill={series.primary} radius={[4, 4, 0, 0]} maxBarSize={44}>
                <LabelList dataKey="correct_result_pct" position="top" formatter={(v) => `${v}%`}
                  style={{ fontSize: 11, fill: C.slate600, fontWeight: 700 }} />
              </Bar>
              {/* Green, not grey: the baseline bar was the palest thing on a white
                  card, which made the one comparison the chart exists for the
                  hardest part of it to read. */}
              <Bar dataKey="always_home_pct" name="Always home" fill={series.accent} radius={[4, 4, 0, 0]} maxBarSize={44} />
            </BarChart>
          </ResponsiveContainer>

          {/* The gap per season, stated rather than left to be eyeballed off the
              bars — including any season where it is negative. */}
          <div style={{ display: "flex", gap: space.lg, flexWrap: "wrap", marginTop: space.md }}>
            {rows.map((s) => (
              <div key={s.season} style={{ ...type.micro, color: C.slate500 }}>
                {s.season}:{" "}
                <span style={{ color: deltaColor(s.edge), fontWeight: 700 }}>
                  {s.edge > 0 ? "+" : ""}{s.edge.toFixed(1)} pts
                </span>{" "}
                over {s.matches} matches
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

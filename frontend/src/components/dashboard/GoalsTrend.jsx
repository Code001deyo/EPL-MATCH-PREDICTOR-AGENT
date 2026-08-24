import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import Card from "../ui/Card";
import EmptyState from "../ui/EmptyState";
import InfoTip from "../ui/InfoTip";
import { C, type } from "../../theme";
import { series, axis, grid, tooltipStyle, legendStyle } from "../charts/chartTheme";

/* Scoring shape of the selected season and division.
 *
 * Takes the already-fetched `league` payload rather than issuing its own request:
 * Dashboard.jsx already calls GET /analytics/league for the summary strip, and a
 * second identical fetch on the same page would be waste. It therefore follows
 * both the season AND the division selector for free. */
export default function GoalsTrend({ league, loading, season, divisionName }) {
  const rows = (league?.goals_by_matchweek || []).slice(-20);

  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <span style={{ ...type.section, color: C.slate800 }}>Scoring trend</span>
        <InfoTip label="About the scoring trend">
          Goals scored per matchweek, home against away, for {season || "the selected season"}
          {divisionName ? ` in the ${divisionName}` : ""}.
          {rows.length ? ` Showing ${rows.length} matchweek${rows.length === 1 ? "" : "s"}.` : ""}
          {" "}Championship rounds are derived from fixture dates, because the source files
          carry no round number.
        </InfoTip>
      </div>

      {loading && <EmptyState kind="loading" />}
      {!loading && rows.length === 0 && (
        <EmptyState kind="not-measured" title="No matchweeks played yet"
          detail="A season that has just started has nothing to trend." />
      )}

      {!loading && rows.length > 0 && (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="matchweek" {...axis} />
            <YAxis {...axis} allowDecimals={false} />
            <Tooltip {...tooltipStyle} labelFormatter={(l) => `Matchweek ${l}`} />
            <Legend wrapperStyle={legendStyle} />
            {/* Dots only when the series is too short to read as a line. */}
            <Line type="monotone" dataKey="home_goals" name="Home goals"
              stroke={series.primary} strokeWidth={2} dot={rows.length <= 3} />
            <Line type="monotone" dataKey="away_goals" name="Away goals"
              stroke={series.accent} strokeWidth={2} dot={rows.length <= 3} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

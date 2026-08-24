import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import EmptyState from "../ui/EmptyState";
import { series, axis, grid, tooltipStyle, legendStyle } from "../charts/chartTheme";

/* Scoring shape of the selected season.
 *
 * Takes the already-fetched `league` payload rather than issuing its own request:
 * Dashboard.jsx already calls GET /analytics/league?season=… for the league
 * context panel, and a second identical fetch on the same page would be waste.
 *
 * This is also what finally makes the dashboard's season selector do something
 * beyond one panel. */
export default function GoalsTrend({ league, loading, season }) {
  const rows = (league?.goals_by_matchweek || []).slice(-20);

  return (
    <Card>
      {/* The caption states the real count. Saying "last 20 matchweeks" against a
          season one week old described a window that does not exist. */}
      <SectionTitle sub={`Goals scored per matchweek in ${season || "the selected season"}, home against away.${
        rows.length ? ` ${rows.length} matchweek${rows.length === 1 ? "" : "s"} played${rows.length === 20 ? " (most recent 20)" : ""}.` : ""
      }`}>
        Scoring trend
      </SectionTitle>

      {loading && <EmptyState kind="loading" />}
      {!loading && rows.length === 0 && (
        <EmptyState kind="not-measured" title="No matchweeks played yet"
          detail="A season that has just started has nothing to trend. This is an absent measurement, not a zero." />
      )}

      {!loading && rows.length > 0 && (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="matchweek" {...axis} />
            <YAxis {...axis} allowDecimals={false} />
            <Tooltip {...tooltipStyle} labelFormatter={(l) => `Matchweek ${l}`} />
            <Legend wrapperStyle={legendStyle} />
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

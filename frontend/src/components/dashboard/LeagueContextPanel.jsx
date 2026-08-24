import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import Stat from "../ui/Stat";
import EmptyState from "../ui/EmptyState";
import { C } from "../../theme";

// League context — secondary to model performance. Describes the league,
// not the model, so it is deliberately quieter: muted card, smaller stats,
// no brand-green chart fills competing with the performance band above.
export default function LeagueContextPanel({ league, loading, season }) {
  const top6Form =
    league?.form_table?.slice(0, 6).map((t) => ({ team: t.team.replace("'", ""), pts: t.last5_pts })) || [];

  return (
    <Card muted>
      <SectionTitle sub={`${season} season`}>League Context</SectionTitle>

      {loading && <EmptyState kind="loading" title="Loading league data…" />}

      {!loading && !league && (
        <EmptyState kind="not-measured" title="Not yet measured" detail="No league data available for this season." />
      )}

      {!loading && league && (
        <>
          <div style={{ display: "flex", gap: 28, flexWrap: "wrap", marginBottom: 20 }}>
            <Stat label="Goals / game" value={fmtNum(league.avg_goals_per_game)} />
            <Stat label="Home win rate" value={fmtPct(league.home_win_rate)} />
            <Stat label="Draw rate" value={fmtPct(league.draw_rate)} />
            <Stat label="Away win rate" value={fmtPct(league.away_win_rate)} />
          </div>

          {top6Form.length > 0 ? (
            <>
              <div style={{ fontSize: 12, color: C.slate500, fontWeight: 600, marginBottom: 8 }}>
                Form points, last 5 games — top 6
              </div>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={top6Form} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" domain={[0, 15]} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="team" tick={{ fontSize: 11 }} width={80} />
                  <Tooltip formatter={(v) => [`${v} pts`, "Form points"]} />
                  <Bar dataKey="pts" fill={C.navy} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </>
          ) : (
            <EmptyState kind="not-measured" title="Not yet measured" detail="No form data available for this season." />
          )}
        </>
      )}
    </Card>
  );
}

function fmtPct(v) {
  return Number.isFinite(v) ? `${(v * 100).toFixed(0)}%` : "not measured";
}
function fmtNum(v) {
  return Number.isFinite(v) ? v : "not measured";
}

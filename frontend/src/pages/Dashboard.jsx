import { useState, useEffect } from "react";
import axios from "axios";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from "recharts";
import KpiCard from "../components/ui/KpiCard";
import Badge, { resultVariant } from "../components/ui/Badge";
import { C, shadow, radius } from "../theme";

const API = "http://localhost:8001";

function Card({ children, style }) {
  return <div style={{ background: C.white, borderRadius: radius.lg, boxShadow: shadow.card, padding: 24, ...style }}>{children}</div>;
}

function SectionTitle({ children }) {
  return <div style={{ fontSize: 15, fontWeight: 700, color: C.slate800, marginBottom: 16 }}>{children}</div>;
}

const RESULT_COLORS = { W: C.emerald, D: C.amber, L: C.rose };

export default function Dashboard() {
  const [league, setLeague] = useState(null);
  const [history, setHistory] = useState([]);
  const [perf, setPerf] = useState(null);
  const [season, setSeason] = useState("2025-26");
  const [seasons, setSeasons] = useState([]);

  useEffect(() => {
    axios.get(`${API}/seasons`).then(r => setSeasons(r.data.seasons)).catch(() => {});
  }, []);

  useEffect(() => {
    axios.get(`${API}/analytics/league?season=${season}`).then(r => setLeague(r.data)).catch(() => {});
    axios.get(`${API}/predictions/history`).then(r => setHistory(r.data.predictions.slice(0, 8))).catch(() => {});
    axios.get(`${API}/analytics/model/performance`).then(r => setPerf(r.data)).catch(() => {});
  }, [season]);

  const top6Form = league?.form_table?.slice(0, 6).map(t => ({ team: t.team.replace("'", ""), pts: t.last5_pts, gf: t.gf, ga: t.ga })) || [];
  const goalsByMW = (league?.goals_by_matchweek || []).slice(-15);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, color: C.slate800 }}>Dashboard</div>
          <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>Season overview & prediction performance</div>
        </div>
        <select value={season} onChange={e => setSeason(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 13, background: C.white, color: C.slate700 }}>
          {seasons.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>

      {/* KPI Row */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <KpiCard icon="🔮" label="Total Predictions" value={perf?.total_predictions ?? "—"} sub="all time" color={C.blue} />
        <KpiCard icon="🎯" label="Result Accuracy" value={perf?.total_predictions ? `${(perf.correct_result_accuracy * 100).toFixed(0)}%` : "—"} sub={`${perf?.correct_result_count ?? 0} correct W/D/L`} color={C.emerald} />
        <KpiCard icon="✅" label="Exact Score %" value={perf?.total_predictions ? `${(perf.exact_score_accuracy * 100).toFixed(0)}%` : "—"} sub={`${perf?.exact_score_count ?? 0} exact scores`} color={C.amber} />
        <KpiCard icon="📊" label="Avg Confidence" value={perf?.avg_confidence ? `${(perf.avg_confidence * 100).toFixed(0)}%` : "—"} sub="model certainty" color={C.blue} />
        <KpiCard icon="⚽" label="Goals / Game" value={league?.avg_goals_per_game ?? "—"} sub={`${season} season`} color={C.rose} />
        <KpiCard icon="🏠" label="Home Win Rate" value={league?.home_win_rate ? `${(league.home_win_rate * 100).toFixed(0)}%` : "—"} sub={`Draw ${league ? (league.draw_rate * 100).toFixed(0) : "—"}%`} color={C.slate600} />
      </div>

      {/* Charts Row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
        <Card>
          <SectionTitle>🏆 Top 6 Form (Last 5 Games)</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={top6Form} layout="vertical" margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" domain={[0, 15]} tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="team" tick={{ fontSize: 11 }} width={80} />
              <Tooltip formatter={v => [`${v} pts`, "Form Points"]} />
              <Bar dataKey="pts" fill={C.blue} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <SectionTitle>📈 Goals per Matchweek</SectionTitle>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={goalsByMW} margin={{ right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="matchweek" tick={{ fontSize: 11 }} label={{ value: "MW", position: "insideBottomRight", offset: -5, fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="home_goals" name="Home Goals" stackId="a" fill={C.blue} />
              <Bar dataKey="away_goals" name="Away Goals" stackId="a" fill={C.rose} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Latest Predictions */}
      <Card>
        <SectionTitle>🕐 Latest Predictions</SectionTitle>
        {history.length === 0 ? (
          <p style={{ color: C.slate400, fontSize: 13 }}>No predictions yet. Go to Predict to get started.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${C.slate100}` }}>
                {["Fixture", "Season", "MW", "Predicted", "Actual", "Result", "Confidence"].map(h => (
                  <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontWeight: 600, color: C.slate500, fontSize: 11, textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map(p => {
                const variant = resultVariant(p.predicted, p.actual);
                return (
                  <tr key={p.id} style={{ borderBottom: `1px solid ${C.slate100}` }}>
                    <td style={{ padding: "10px 12px", fontWeight: 500, color: C.slate800 }}>{p.fixture}</td>
                    <td style={{ padding: "10px 12px", color: C.slate500 }}>{p.season}</td>
                    <td style={{ padding: "10px 12px", color: C.slate500 }}>MW{p.matchweek}</td>
                    <td style={{ padding: "10px 12px", fontWeight: 700, color: C.blue, fontSize: 15 }}>{p.predicted}</td>
                    <td style={{ padding: "10px 12px", color: C.slate600 }}>{p.actual || "—"}</td>
                    <td style={{ padding: "10px 12px" }}><Badge variant={variant} small /></td>
                    <td style={{ padding: "10px 12px", color: C.slate500 }}>{p.confidence ? `${(p.confidence * 100).toFixed(0)}%` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

import { useState, useEffect } from "react";
import axios from "axios";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from "recharts";
import KpiCard from "../components/ui/KpiCard";
import { C, shadow, radius } from "../theme";

const API = "http://localhost:8001";

function Card({ children, style }) {
  return <div style={{ background: C.white, borderRadius: radius.lg, boxShadow: shadow.card, padding: 24, ...style }}>{children}</div>;
}

function SectionTitle({ children }) {
  return <div style={{ fontSize: 15, fontWeight: 700, color: C.slate800, marginBottom: 16 }}>{children}</div>;
}

function FormBadge({ char }) {
  const map = { W: { bg: "#d1fae5", color: C.emerald }, D: { bg: "#fef3c7", color: "#92400e" }, L: { bg: "#fee2e2", color: C.rose } };
  const s = map[char] || { bg: C.slate100, color: C.slate400 };
  return <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: 4, background: s.bg, color: s.color, fontSize: 11, fontWeight: 700 }}>{char}</span>;
}

export default function Analytics() {
  const [league, setLeague] = useState(null);
  const [season, setSeason] = useState("2025-26");
  const [seasons, setSeasons] = useState([]);
  const [h2hHome, setH2hHome] = useState("");
  const [h2hAway, setH2hAway] = useState("");
  const [h2h, setH2h] = useState(null);
  const [teams, setTeams] = useState([]);

  useEffect(() => {
    axios.get(`${API}/seasons`).then(r => setSeasons(r.data.seasons)).catch(() => {});
    axios.get(`${API}/teams`).then(r => { setTeams(r.data.teams); setH2hHome(r.data.teams[0] || ""); setH2hAway(r.data.teams[1] || ""); }).catch(() => {});
  }, []);

  useEffect(() => {
    axios.get(`${API}/analytics/league?season=${season}`).then(r => setLeague(r.data)).catch(() => {});
  }, [season]);

  const fetchH2H = () => {
    if (!h2hHome || !h2hAway || h2hHome === h2hAway) return;
    axios.get(`${API}/analytics/head-to-head?home=${encodeURIComponent(h2hHome)}&away=${encodeURIComponent(h2hAway)}`).then(r => setH2h(r.data)).catch(() => {});
  };

  useEffect(() => { if (h2hHome && h2hAway) fetchH2H(); }, [h2hHome, h2hAway]);

  const goalsByMW = (league?.goals_by_matchweek || []).slice(-20);
  const topScoring = league?.top_scoring_teams || [];
  const formTable = league?.form_table || [];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, color: C.slate800 }}>Analytics</div>
          <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>League statistics & head-to-head analysis</div>
        </div>
        <select value={season} onChange={e => setSeason(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 13, background: C.white }}>
          {seasons.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>

      {/* League KPIs */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <KpiCard icon="⚽" label="Avg Goals / Game" value={league?.avg_goals_per_game ?? "—"} color={C.blue} />
        <KpiCard icon="🏠" label="Home Win Rate" value={league ? `${(league.home_win_rate * 100).toFixed(0)}%` : "—"} color={C.emerald} />
        <KpiCard icon="🤝" label="Draw Rate" value={league ? `${(league.draw_rate * 100).toFixed(0)}%` : "—"} color={C.amber} />
        <KpiCard icon="✈️" label="Away Win Rate" value={league ? `${(league.away_win_rate * 100).toFixed(0)}%` : "—"} color={C.rose} />
        <KpiCard icon="🎮" label="Matches Played" value={league?.total_matches ?? "—"} color={C.slate600} />
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
        <Card>
          <SectionTitle>📈 Goals per Matchweek</SectionTitle>
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={goalsByMW}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="matchweek" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="home_goals" name="Home Goals" stroke={C.blue} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="away_goals" name="Away Goals" stroke={C.rose} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <SectionTitle>🏆 Top Attacking Teams</SectionTitle>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={topScoring} layout="vertical" margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="team" tick={{ fontSize: 11 }} width={85} />
              <Tooltip />
              <Bar dataKey="goals" fill={C.emerald} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* H2H Explorer */}
      <Card style={{ marginBottom: 24 }}>
        <SectionTitle>⚔️ Head-to-Head Explorer</SectionTitle>
        <div style={{ display: "flex", gap: 12, marginBottom: 20, alignItems: "flex-end" }}>
          {[["Home Team", h2hHome, setH2hHome], ["Away Team", h2hAway, setH2hAway]].map(([label, val, setter]) => (
            <div key={label} style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: C.slate500, marginBottom: 5, textTransform: "uppercase" }}>{label}</label>
              <select value={val} onChange={e => setter(e.target.value)}
                style={{ width: "100%", padding: "9px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 14, background: C.white }}>
                {teams.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
          ))}
        </div>

        {h2h && h2h.total_meetings > 0 && (
          <>
            <div style={{ display: "flex", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
              {[
                ["Total Meetings", h2h.total_meetings, C.slate600],
                [`${h2h.home_team} Wins`, h2h.home_wins, C.blue],
                ["Draws", h2h.draws, C.amber],
                [`${h2h.away_team} Wins`, h2h.away_wins, C.rose],
                ["Avg Goals", h2h.avg_goals, C.emerald],
              ].map(([label, val, color]) => (
                <div key={label} style={{ flex: 1, minWidth: 100, textAlign: "center", padding: "14px 10px", background: C.slate50, borderRadius: radius.md }}>
                  <div style={{ fontSize: 24, fontWeight: 700, color }}>{val}</div>
                  <div style={{ fontSize: 11, color: C.slate400, marginTop: 4 }}>{label}</div>
                </div>
              ))}
            </div>

            <div style={{ fontSize: 13, fontWeight: 600, color: C.slate600, marginBottom: 10 }}>Last 5 Meetings</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `2px solid ${C.slate100}` }}>
                  {["Date", "Home", "Score", "Away", "Season"].map(h => (
                    <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: C.slate400, textTransform: "uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {h2h.last_5.map((m, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${C.slate100}` }}>
                    <td style={{ padding: "9px 12px", color: C.slate500 }}>{m.date}</td>
                    <td style={{ padding: "9px 12px", fontWeight: 500, color: C.slate800 }}>{m.home_team}</td>
                    <td style={{ padding: "9px 12px", fontWeight: 700, color: C.blue }}>{m.score}</td>
                    <td style={{ padding: "9px 12px", fontWeight: 500, color: C.slate800 }}>{m.away_team}</td>
                    <td style={{ padding: "9px 12px", color: C.slate400 }}>{m.season}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {h2h && h2h.total_meetings === 0 && <p style={{ color: C.slate400, fontSize: 13 }}>No meetings found between these teams.</p>}
      </Card>

      {/* Form Table */}
      <Card>
        <SectionTitle>📋 League Table — {season}</SectionTitle>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${C.slate100}` }}>
                {["#", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Last 5"].map(h => (
                  <th key={h} style={{ padding: "8px 12px", textAlign: h === "Team" ? "left" : "center", fontSize: 11, fontWeight: 600, color: C.slate400, textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {formTable.map((t, i) => (
                <tr key={t.team} style={{ borderBottom: `1px solid ${C.slate100}`, background: i < 4 ? "#f0f9ff" : i >= formTable.length - 3 ? "#fff5f5" : "transparent" }}>
                  <td style={{ padding: "9px 12px", textAlign: "center", fontWeight: 700, color: i < 4 ? C.blue : i >= formTable.length - 3 ? C.rose : C.slate400 }}>{i + 1}</td>
                  <td style={{ padding: "9px 12px", fontWeight: 600, color: C.slate800 }}>{t.team}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", color: C.slate600 }}>{t.played}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", color: C.emerald, fontWeight: 600 }}>{t.won}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", color: C.amber }}>{t.drawn}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", color: C.rose }}>{t.lost}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", color: C.slate600 }}>{t.gf}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", color: C.slate600 }}>{t.ga}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", color: t.gd >= 0 ? C.emerald : C.rose, fontWeight: 600 }}>{t.gd > 0 ? `+${t.gd}` : t.gd}</td>
                  <td style={{ padding: "9px 12px", textAlign: "center", fontWeight: 700, color: C.slate800 }}>{t.pts}</td>
                  <td style={{ padding: "9px 12px" }}>
                    <div style={{ display: "flex", gap: 3 }}>
                      {(t.last5 || "").split("").map((c, j) => <FormBadge key={j} char={c} />)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 12, fontSize: 11, color: C.slate400, display: "flex", gap: 16 }}>
          <span style={{ color: C.blue }}>■ Champions League</span>
          <span style={{ color: C.rose }}>■ Relegation Zone</span>
        </div>
      </Card>
    </div>
  );
}

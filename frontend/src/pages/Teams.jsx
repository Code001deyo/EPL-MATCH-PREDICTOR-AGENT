import { useState, useEffect } from "react";
import axios from "axios";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from "recharts";
import KpiCard from "../components/ui/KpiCard";
import { C, shadow, radius } from "../theme";

const API = "http://localhost:8001";

function Card({ children, style }) {
  return <div style={{ background: C.white, borderRadius: radius.lg, boxShadow: shadow.card, padding: 24, ...style }}>{children}</div>;
}

function SectionTitle({ children }) {
  return <div style={{ fontSize: 15, fontWeight: 700, color: C.slate800, marginBottom: 16 }}>{children}</div>;
}

export default function Teams() {
  const [teams, setTeams] = useState([]);
  const [selected, setSelected] = useState("");
  const [stats, setStats] = useState(null);
  const [form, setForm] = useState(null);

  useEffect(() => {
    axios.get(`${API}/teams`).then(r => { setTeams(r.data.teams); setSelected(r.data.teams[0] || ""); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) return;
    setStats(null); setForm(null);
    axios.get(`${API}/team/${encodeURIComponent(selected)}/stats?last_n=15`).then(r => setStats(r.data)).catch(() => {});
    axios.get(`${API}/analytics/team/${encodeURIComponent(selected)}/form`).then(r => setForm(r.data)).catch(() => {});
  }, [selected]);

  const chartData = stats?.last_matches?.slice().reverse().map((m, i) => ({
    match: i + 1, gf: m.gf, ga: m.ga, opponent: m.opponent, venue: m.venue,
  })) || [];

  const formData = form?.last_matches?.slice().reverse().map((m, i) => ({
    match: i + 1, pts: m.result === "W" ? 3 : m.result === "D" ? 1 : 0,
    result: m.result, opponent: m.opponent, gf: m.gf, ga: m.ga,
  })) || [];

  const ptColor = (pts) => pts === 3 ? C.emerald : pts === 1 ? C.amber : C.rose;

  const played = form?.last_matches?.length || 0;
  const wins = form?.last_matches?.filter(m => m.result === "W").length || 0;
  const draws = form?.last_matches?.filter(m => m.result === "D").length || 0;
  const losses = form?.last_matches?.filter(m => m.result === "L").length || 0;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: C.slate800 }}>Teams</div>
        <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>Deep-dive team performance analysis</div>
      </div>

      <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 24 }}>
        <div style={{ flex: "0 0 280px" }}>
          <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: C.slate500, marginBottom: 5, textTransform: "uppercase" }}>Select Team</label>
          <select value={selected} onChange={e => setSelected(e.target.value)}
            style={{ width: "100%", padding: "10px 14px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 15, fontWeight: 600, background: C.white, color: C.slate800 }}>
            {teams.map(t => <option key={t}>{t}</option>)}
          </select>
        </div>
        {form && (
          <div style={{ display: "flex", gap: 12, flex: 1, flexWrap: "wrap" }}>
            <KpiCard icon="📊" label="Last 15 Played" value={played} color={C.slate600} />
            <KpiCard icon="✅" label="Wins" value={wins} color={C.emerald} />
            <KpiCard icon="🤝" label="Draws" value={draws} color={C.amber} />
            <KpiCard icon="❌" label="Losses" value={losses} color={C.rose} />
            <KpiCard icon="⚽" label="Avg Scored" value={form.avg_gf_last5} sub="last 5" color={C.blue} />
            <KpiCard icon="🛡️" label="Avg Conceded" value={form.avg_ga_last5} sub="last 5" color={C.rose} />
          </div>
        )}
      </div>

      {form && (
        <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
          {[
            ["Form", form.form_string, C.slate700],
            ["Last 5 Pts", form.last5_pts, C.blue],
            ["BTTS Rate", `${(form.btts_rate * 100).toFixed(0)}%`, C.amber],
            ["Over 2.5 Rate", `${(form.over_2_5_rate * 100).toFixed(0)}%`, C.emerald],
            ["Clean Sheet Rate", `${(form.clean_sheet_rate * 100).toFixed(0)}%`, C.slate600],
          ].map(([label, val, color]) => (
            <div key={label} style={{ flex: 1, minWidth: 120, padding: "14px 16px", background: C.white, borderRadius: radius.md, boxShadow: shadow.card, textAlign: "center" }}>
              <div style={{ fontSize: 20, fontWeight: 700, color, letterSpacing: label === "Form" ? 4 : 0 }}>{val}</div>
              <div style={{ fontSize: 11, color: C.slate400, marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {chartData.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
          <Card>
            <SectionTitle>⚽ Goals Scored vs Conceded (Last 15)</SectionTitle>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="match" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={i => `vs ${chartData[i - 1]?.opponent} (${chartData[i - 1]?.venue})`} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="gf" name="Scored" stroke={C.emerald} strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="ga" name="Conceded" stroke={C.rose} strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          <Card>
            <SectionTitle>📊 Form Points (Last 15 Matches)</SectionTitle>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={formData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="match" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 3]} ticks={[0, 1, 3]} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v, n, p) => [p.payload.result === "W" ? "Win" : p.payload.result === "D" ? "Draw" : "Loss", `vs ${p.payload.opponent}`]} />
                <Bar dataKey="pts" radius={[4, 4, 0, 0]}>
                  {formData.map((entry, i) => <Cell key={i} fill={ptColor(entry.pts)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}

      {/* Recent Results Table */}
      {form?.last_matches?.length > 0 && (
        <Card>
          <SectionTitle>📋 Recent Results</SectionTitle>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${C.slate100}` }}>
                {["Date", "Opponent", "Venue", "Score", "Result"].map(h => (
                  <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: C.slate400, textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {form.last_matches.map((m, i) => {
                const rColor = m.result === "W" ? C.emerald : m.result === "D" ? C.amber : C.rose;
                return (
                  <tr key={i} style={{ borderBottom: `1px solid ${C.slate100}` }}>
                    <td style={{ padding: "9px 12px", color: C.slate500 }}>{m.date}</td>
                    <td style={{ padding: "9px 12px", fontWeight: 500, color: C.slate800 }}>{m.opponent}</td>
                    <td style={{ padding: "9px 12px" }}>
                      <span style={{ background: m.venue === "H" ? "#dbeafe" : "#fce7f3", color: m.venue === "H" ? C.blue : "#9d174d", padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600 }}>
                        {m.venue === "H" ? "Home" : "Away"}
                      </span>
                    </td>
                    <td style={{ padding: "9px 12px", fontWeight: 700, color: C.slate800 }}>{m.gf} – {m.ga}</td>
                    <td style={{ padding: "9px 12px" }}>
                      <span style={{ background: rColor + "22", color: rColor, padding: "3px 10px", borderRadius: 12, fontSize: 12, fontWeight: 700 }}>{m.result}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

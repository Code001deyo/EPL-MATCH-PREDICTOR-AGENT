import React, { useState, useEffect } from "react";
import axios from "axios";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

const API = "http://localhost:8001";

export default function TeamStats({ teams }) {
  const [selected, setSelected] = useState("");
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (!selected) return;
    axios.get(`${API}/team/${encodeURIComponent(selected)}/stats?last_n=15`)
      .then((r) => setStats(r.data))
      .catch(() => setStats(null));
  }, [selected]);

  const chartData = stats?.last_matches
    .slice()
    .reverse()
    .map((m, i) => ({ match: i + 1, gf: m.gf, ga: m.ga, opponent: m.opponent, venue: m.venue }));

  return (
    <div style={styles.container}>
      <h3>Team Performance</h3>
      <select value={selected} onChange={(e) => setSelected(e.target.value)} style={styles.select}>
        <option value="">Select a team...</option>
        {teams.map((t) => <option key={t}>{t}</option>)}
      </select>

      {chartData && (
        <div style={{ marginTop: 24 }}>
          <p style={styles.subtitle}>Goals Scored vs Conceded — Last 15 Matches</p>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="match" label={{ value: "Match", position: "insideBottom", offset: -2 }} />
              <YAxis allowDecimals={false} />
              <Tooltip formatter={(v, n, p) => [v, n]} labelFormatter={(i) => `vs ${chartData[i - 1]?.opponent} (${chartData[i - 1]?.venue})`} />
              <Legend />
              <Line type="monotone" dataKey="gf" stroke="#38a169" name="Goals Scored" strokeWidth={2} dot={{ r: 4 }} />
              <Line type="monotone" dataKey="ga" stroke="#e53e3e" name="Goals Conceded" strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { maxWidth: 700, margin: "32px auto", padding: 24, borderRadius: 12, boxShadow: "0 4px 24px rgba(0,0,0,0.08)", fontFamily: "sans-serif" },
  select: { padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e0", fontSize: 14, width: "100%" },
  subtitle: { color: "#718096", fontSize: 13, marginBottom: 8 },
};

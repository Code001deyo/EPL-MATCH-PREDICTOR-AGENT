import { useState, useEffect, useMemo } from "react";
import axios from "axios";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import KpiCard from "../components/ui/KpiCard";
import Badge, { resultVariant } from "../components/ui/Badge";
import { C, shadow, radius } from "../theme";

const API = "http://localhost:8001";

function Card({ children, style }) {
  return <div style={{ background: C.white, borderRadius: radius.lg, boxShadow: shadow.card, padding: 24, ...style }}>{children}</div>;
}

export default function History() {
  const [history, setHistory] = useState([]);
  const [filterResult, setFilterResult] = useState("all");
  const [filterSeason, setFilterSeason] = useState("all");

  useEffect(() => {
    axios.get(`${API}/predictions/history`).then(r => setHistory(r.data.predictions)).catch(() => {});
  }, []);

  const seasons = useMemo(() => ["all", ...new Set(history.map(p => p.season))], [history]);

  const filtered = useMemo(() => history.filter(p => {
    const variant = resultVariant(p.predicted, p.actual);
    const seasonOk = filterSeason === "all" || p.season === filterSeason;
    const resultOk = filterResult === "all" || variant === filterResult;
    return seasonOk && resultOk;
  }), [history, filterResult, filterSeason]);

  const evaluated = history.filter(p => p.actual && !p.actual.includes("null"));
  const exact = evaluated.filter(p => resultVariant(p.predicted, p.actual) === "exact").length;
  const correct = evaluated.filter(p => ["exact", "result"].includes(resultVariant(p.predicted, p.actual))).length;

  // Rolling 10-prediction accuracy trend
  const trendData = useMemo(() => {
    const ev = [...evaluated].reverse();
    return ev.map((_, i) => {
      if (i < 9) return null;
      const window = ev.slice(i - 9, i + 1);
      const correctInWindow = window.filter(p => ["exact", "result"].includes(resultVariant(p.predicted, p.actual))).length;
      return { prediction: i + 1, accuracy: Math.round((correctInWindow / 10) * 100) };
    }).filter(Boolean);
  }, [evaluated]);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: C.slate800 }}>Prediction History</div>
        <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>Track record of all predictions vs actual results</div>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <KpiCard icon="🔮" label="Total Predictions" value={history.length} color={C.blue} />
        <KpiCard icon="🎯" label="Result Accuracy" value={evaluated.length ? `${Math.round((correct / evaluated.length) * 100)}%` : "—"} sub={`${correct} / ${evaluated.length} evaluated`} color={C.emerald} />
        <KpiCard icon="✅" label="Exact Score %" value={evaluated.length ? `${Math.round((exact / evaluated.length) * 100)}%` : "—"} sub={`${exact} exact scores`} color={C.amber} />
        <KpiCard icon="⏳" label="Pending" value={history.length - evaluated.length} color={C.slate400} />
      </div>

      {/* Accuracy Trend */}
      {trendData.length > 0 && (
        <Card style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: C.slate800, marginBottom: 16 }}>📈 Rolling Accuracy (10-Prediction Window)</div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="prediction" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={v => [`${v}%`, "Result Accuracy"]} />
              <Line type="monotone" dataKey="accuracy" stroke={C.blue} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Filters + Table */}
      <Card>
        <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: C.slate800, flex: 1 }}>All Predictions</div>
          <select value={filterSeason} onChange={e => setFilterSeason(e.target.value)}
            style={{ padding: "7px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 13, background: C.white }}>
            {seasons.map(s => <option key={s} value={s}>{s === "all" ? "All Seasons" : s}</option>)}
          </select>
          <select value={filterResult} onChange={e => setFilterResult(e.target.value)}
            style={{ padding: "7px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 13, background: C.white }}>
            <option value="all">All Results</option>
            <option value="exact">✅ Exact Score</option>
            <option value="result">🟡 Correct Result</option>
            <option value="wrong">❌ Wrong</option>
            <option value="pending">⏳ Pending</option>
          </select>
          <span style={{ fontSize: 12, color: C.slate400 }}>{filtered.length} predictions</span>
        </div>

        {filtered.length === 0 ? (
          <p style={{ color: C.slate400, fontSize: 13 }}>No predictions match the current filters.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `2px solid ${C.slate100}` }}>
                  {["Fixture", "Season", "MW", "Predicted", "Actual", "Result", "H Win%", "Draw%", "A Win%", "Conf", "Date"].map(h => (
                    <th key={h} style={{ padding: "8px 10px", textAlign: "left", fontSize: 11, fontWeight: 600, color: C.slate400, textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(p => {
                  const variant = resultVariant(p.predicted, p.actual);
                  return (
                    <tr key={p.id} style={{ borderBottom: `1px solid ${C.slate100}` }}>
                      <td style={{ padding: "9px 10px", fontWeight: 500, color: C.slate800, whiteSpace: "nowrap" }}>{p.fixture}</td>
                      <td style={{ padding: "9px 10px", color: C.slate500 }}>{p.season}</td>
                      <td style={{ padding: "9px 10px", color: C.slate500 }}>MW{p.matchweek}</td>
                      <td style={{ padding: "9px 10px", fontWeight: 700, color: C.blue, fontSize: 15 }}>{p.predicted}</td>
                      <td style={{ padding: "9px 10px", fontWeight: 600, color: C.slate700 }}>{p.actual || "—"}</td>
                      <td style={{ padding: "9px 10px" }}><Badge variant={variant} small /></td>
                      <td style={{ padding: "9px 10px", color: C.blue }}>{p.home_win_prob ? `${(p.home_win_prob * 100).toFixed(0)}%` : "—"}</td>
                      <td style={{ padding: "9px 10px", color: C.amber }}>{p.draw_prob ? `${(p.draw_prob * 100).toFixed(0)}%` : "—"}</td>
                      <td style={{ padding: "9px 10px", color: C.rose }}>{p.away_win_prob ? `${(p.away_win_prob * 100).toFixed(0)}%` : "—"}</td>
                      <td style={{ padding: "9px 10px", color: C.slate500 }}>{p.confidence ? `${(p.confidence * 100).toFixed(0)}%` : "—"}</td>
                      <td style={{ padding: "9px 10px", color: C.slate400, fontSize: 11, whiteSpace: "nowrap" }}>{(p.created_at || "").slice(0, 10)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

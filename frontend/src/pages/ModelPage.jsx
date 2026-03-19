import { useState, useEffect } from "react";
import axios from "axios";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend } from "recharts";
import KpiCard from "../components/ui/KpiCard";
import { C, shadow, radius } from "../theme";

const API = "http://localhost:8001";

function Card({ children, style }) {
  return <div style={{ background: C.white, borderRadius: radius.lg, boxShadow: shadow.card, padding: 24, ...style }}>{children}</div>;
}

function SectionTitle({ children }) {
  return <div style={{ fontSize: 15, fontWeight: 700, color: C.slate800, marginBottom: 16 }}>{children}</div>;
}

export default function ModelPage() {
  const [perf, setPerf] = useState(null);
  const [retraining, setRetraining] = useState(false);
  const [retrainResult, setRetrainResult] = useState(null);
  const [lastTrained, setLastTrained] = useState(null);

  const fetchPerf = () => {
    axios.get(`${API}/analytics/model/performance`).then(r => setPerf(r.data)).catch(() => {});
  };

  useEffect(() => { fetchPerf(); }, []);

  const handleRetrain = async () => {
    setRetraining(true); setRetrainResult(null);
    try {
      const { data } = await axios.post(`${API}/model/retrain`);
      setRetrainResult(data);
      setLastTrained(new Date().toLocaleString());
      fetchPerf();
    } catch (e) {
      setRetrainResult({ error: e.response?.data?.detail || "Retrain failed." });
    } finally { setRetraining(false); }
  };

  const evaluated = perf?.evaluated || 0;
  const exact = perf?.exact_score_count || 0;
  const correctResult = perf?.correct_result_count || 0;
  const wrong = perf?.wrong_count || 0;
  const pending = (perf?.total_predictions || 0) - evaluated;

  const donutData = evaluated > 0 ? [
    { name: "Exact Score", value: exact, color: C.emerald },
    { name: "Correct Result", value: correctResult - exact, color: C.amber },
    { name: "Wrong", value: wrong, color: C.rose },
  ] : [];

  const monthlyData = (perf?.by_month || []).map(m => ({
    month: m.month,
    "Result %": Math.round(m.correct_result_pct * 100),
    "Exact %": Math.round(m.exact_score_pct * 100),
  }));

  const metrics = retrainResult?.metrics || {};

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: C.slate800 }}>Model Performance</div>
        <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>XGBoost model metrics and retraining controls</div>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <KpiCard icon="🔮" label="Total Predictions" value={perf?.total_predictions ?? "—"} color={C.blue} />
        <KpiCard icon="📊" label="Evaluated" value={evaluated} sub="with actual results" color={C.slate600} />
        <KpiCard icon="🎯" label="Result Accuracy" value={evaluated ? `${(perf.correct_result_accuracy * 100).toFixed(0)}%` : "—"} color={C.emerald} />
        <KpiCard icon="✅" label="Exact Score %" value={evaluated ? `${(perf.exact_score_accuracy * 100).toFixed(0)}%` : "—"} color={C.amber} />
        <KpiCard icon="💡" label="Avg Confidence" value={perf?.avg_confidence ? `${(perf.avg_confidence * 100).toFixed(0)}%` : "—"} color={C.blue} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
        {/* Donut Chart */}
        <Card>
          <SectionTitle>🎯 Prediction Accuracy Breakdown</SectionTitle>
          {donutData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={donutData} cx="50%" cy="50%" innerRadius={60} outerRadius={90} paddingAngle={3} dataKey="value">
                    {donutData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip formatter={(v, n) => [v, n]} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", justifyContent: "center", gap: 20, marginTop: 8 }}>
                {donutData.map(d => (
                  <div key={d.name} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 2, background: d.color }} />
                    <span style={{ color: C.slate600 }}>{d.name}: <strong>{d.value}</strong></span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ textAlign: "center", color: C.slate300, padding: "40px 0" }}>
              <div style={{ fontSize: 36 }}>📊</div>
              <div style={{ fontSize: 13, marginTop: 8 }}>No evaluated predictions yet</div>
            </div>
          )}
        </Card>

        {/* Monthly Accuracy */}
        <Card>
          <SectionTitle>📅 Monthly Accuracy Trend</SectionTitle>
          {monthlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <Tooltip unit="%" />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Result %" fill={C.blue} radius={[3, 3, 0, 0]} />
                <Bar dataKey="Exact %" fill={C.emerald} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ textAlign: "center", color: C.slate300, padding: "40px 0" }}>
              <div style={{ fontSize: 36 }}>📅</div>
              <div style={{ fontSize: 13, marginTop: 8 }}>No monthly data yet</div>
            </div>
          )}
        </Card>
      </div>

      {/* Retrain Card */}
      <Card>
        <SectionTitle>🔄 Model Retraining</SectionTitle>
        <div style={{ display: "flex", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 13, color: C.slate500, marginBottom: 16, lineHeight: 1.6 }}>
              Retrain the XGBoost models on all available match data. This updates the home goals and away goals prediction models with the latest results.
              Training uses 80/20 walk-forward validation split.
            </p>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <button onClick={handleRetrain} disabled={retraining}
                style={{ padding: "11px 28px", background: retraining ? C.slate300 : C.blue, color: C.white, border: "none", borderRadius: radius.sm, fontSize: 14, fontWeight: 700, cursor: retraining ? "default" : "pointer" }}>
                {retraining ? "⏳ Training..." : "🔄 Retrain Model"}
              </button>
              {lastTrained && <span style={{ fontSize: 12, color: C.slate400 }}>Last trained: {lastTrained}</span>}
            </div>
          </div>

          {retrainResult && (
            <div style={{ flex: 1, padding: "16px 20px", background: retrainResult.error ? "#fff5f5" : "#f0fdf4", borderRadius: radius.md, border: `1px solid ${retrainResult.error ? C.rose : C.emerald}` }}>
              {retrainResult.error ? (
                <p style={{ color: C.rose, fontSize: 13 }}>❌ {retrainResult.error}</p>
              ) : (
                <>
                  <div style={{ fontSize: 13, fontWeight: 700, color: C.emerald, marginBottom: 10 }}>✅ {retrainResult.status}</div>
                  {Object.entries(retrainResult.metrics || {}).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: C.slate600, marginBottom: 4 }}>
                      <span>{k.replace(/_/g, " ")}</span>
                      <strong>{typeof v === "number" ? v.toFixed(4) : v}</strong>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* Model Info */}
        <div style={{ marginTop: 24, padding: "16px 20px", background: C.slate50, borderRadius: radius.md }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: C.slate600, marginBottom: 10 }}>Model Architecture</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, fontSize: 12, color: C.slate500 }}>
            {[
              ["Algorithm", "XGBoost Regressor"],
              ["Models", "Home Goals + Away Goals"],
              ["Features", "35 engineered features"],
              ["Validation", "80/20 walk-forward split"],
              ["Probability", "Poisson distribution"],
              ["Explainability", "Feature importance"],
            ].map(([k, v]) => (
              <div key={k}>
                <div style={{ fontWeight: 600, color: C.slate600, marginBottom: 2 }}>{k}</div>
                <div style={{ color: C.slate400 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend } from "recharts";
import KpiCard from "../components/ui/KpiCard";
import Card from "../components/ui/Card";
import SectionTitle from "../components/ui/SectionTitle";
import EmptyState from "../components/ui/EmptyState";
import RetrainPanel from "../components/model/RetrainPanel";
import ModelArchitecture from "../components/model/ModelArchitecture";
import { C, type, space } from "../theme";
import { series, axis, grid, tooltipStyle, legendStyle } from "../components/charts/chartTheme";
import { useIsCompact } from "../hooks/useBreakpoint";
import { API } from "../config";

export default function ModelPage() {
  const [perf, setPerf] = useState(null);
  const [loading, setLoading] = useState(true);
  const compact = useIsCompact();

  const fetchPerf = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/analytics/model/performance`)
      .then(r => setPerf(r.data))
      .catch(() => setPerf(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchPerf(); }, [fetchPerf]);

  // These counts live under `live_settled`. This page used to read them from the
  // top level, where only `evaluated` and `total_predictions` exist — so exact,
  // correct and wrong were all undefined and defaulted to 0, and the donut
  // rendered three empty slices beside a non-zero "Evaluated" count.
  const live = perf?.live_settled || {};
  const backtested = perf?.backtested || null;

  const evaluated = live.evaluated || 0;
  const exact = live.exact_score_count || 0;
  const correctResult = live.correct_result_count || 0;
  const wrong = live.wrong_count || 0;

  const donutData = evaluated > 0 ? [
    { name: "Exact Score", value: exact, color: C.emerald },
    { name: "Correct Result", value: correctResult - exact, color: C.navyLight },
    { name: "Wrong", value: wrong, color: C.rose },
  ] : [];

  const monthlyData = (live.by_month || []).map(m => ({
    month: m.month,
    "Result %": Math.round(m.correct_result_pct * 100),
    "Exact %": Math.round(m.exact_score_pct * 100),
  }));

  return (
    <div>
      <div style={{ marginBottom: space.xl }}>
        <div style={{ ...type.page, color: C.navy }}>Model Performance</div>
        <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>
          Backtested accuracy and live-settled accuracy, reported separately
        </div>
      </div>

      {/* Backtested and live-settled measure different things: a systematic
          walk-forward simulation versus whatever fixtures users happened to
          click. Averaging them into one headline would hide which is which. */}
      <Card style={{ marginBottom: space.xl }}>
        <SectionTitle level="primary" sub="Walk-forward simulation over completed seasons: refit before each matchweek, then score it.">
          Backtested accuracy
        </SectionTitle>
        {!backtested || !backtested.matches_scored ? (
          <EmptyState kind="not-measured" title="No backtest has been run"
            detail="Run one from the dashboard calibration panel to populate this." />
        ) : (
          <div style={{ display: "flex", gap: space.xxl, flexWrap: "wrap" }}>
            <Figure label="Correct result" value={`${backtested.headline.correct_result_pct}%`}
              sub={`vs ${backtested.headline.always_home_pct}% always-home`} />
            <Figure label="Exact score" value={`${backtested.headline.exact_score_pct}%`} />
            <Figure label="Log loss" value={backtested.headline.log_loss}
              sub={`vs ${backtested.headline.base_rate_log_loss} base rate`} />
            <Figure label="Matches" value={backtested.headline.matches}
              sub={(backtested.seasons_covered || []).join(", ")} />
          </div>
        )}
      </Card>

      <SectionTitle sub="Predictions users actually made, settled against real results. Self-selected, so not a measurement of the model.">
        Live-settled predictions
      </SectionTitle>

      <div style={{ display: "flex", gap: space.lg, marginBottom: space.xl, flexWrap: "wrap" }}>
        <KpiCard label="Total Predictions" value={live.total_predictions ?? "—"} color={C.blue} />
        <KpiCard label="Evaluated" value={evaluated || "—"} sub="with actual results" color={C.slate600} />
        <KpiCard label="Result Accuracy" value={evaluated ? `${(live.correct_result_accuracy * 100).toFixed(0)}%` : "not measured"} color={C.emerald} />
        <KpiCard label="Exact Score %" value={evaluated ? `${(live.exact_score_accuracy * 100).toFixed(0)}%` : "not measured"} color={C.amber} />
        <KpiCard label="Avg Confidence" value={live.avg_confidence ? `${(live.avg_confidence * 100).toFixed(0)}%` : "not measured"} color={C.blue} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: compact ? "1fr" : "1fr 1fr", gap: space.xl, marginBottom: space.xl }}>
        <Card>
          <SectionTitle>Prediction Accuracy Breakdown</SectionTitle>
          {loading ? <EmptyState kind="loading" /> : donutData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={donutData} cx="50%" cy="50%" innerRadius={60} outerRadius={90} paddingAngle={3} dataKey="value">
                    {donutData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip formatter={(v, n) => [v, n]} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", justifyContent: "center", gap: 20, marginTop: 8, flexWrap: "wrap" }}>
                {donutData.map(d => (
                  <div key={d.name} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 2, background: d.color }} />
                    <span style={{ color: C.slate600 }}>{d.name}: <strong>{d.value}</strong></span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <EmptyState kind="not-measured" title="No settled predictions yet"
              detail="A prediction is settled once its fixture has been played." />
          )}
        </Card>

        <Card>
          <SectionTitle>Monthly Accuracy Trend</SectionTitle>
          {loading ? <EmptyState kind="loading" /> : monthlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={monthlyData}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="month" {...axis} />
                <YAxis domain={[0, 100]} {...axis} unit="%" />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={legendStyle} />
                {/* Two greys made these read as one series in two shades. Result
                    and exact-score are different measurements. */}
                <Bar dataKey="Result %" fill={series.primary} radius={[3, 3, 0, 0]} />
                <Bar dataKey="Exact %" fill={series.accent} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState kind="not-measured" title="No monthly data yet" />
          )}
        </Card>
      </div>

      <div style={{ marginBottom: space.xl }}>
        <RetrainPanel onComplete={fetchPerf} />
      </div>

      <ModelArchitecture />
    </div>
  );
}

function Figure({ label, value, sub }) {
  return (
    <div>
      <div style={{ ...type.label, color: C.slate500 }}>{label}</div>
      <div style={{ ...type.stat, color: C.slate800, marginTop: 4 }}>{value}</div>
      {sub && <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

import { useState, useEffect } from "react";
import axios from "axios";
import { C, shadow, radius } from "../theme";
import { API } from "../config";

// Reports where the numbers came from and how fresh they are, so a figure that
// rests on a partial season is not presented with the same authority as one
// backed by complete data.
export default function DataProvenance() {
  const [coverage, setCoverage] = useState(null);
  const [freshness, setFreshness] = useState(null);
  const [apiStatus, setApiStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [cov, fresh, health] = await Promise.all([
          axios.get(`${API}/data/coverage`),
          axios.get(`${API}/data/freshness`),
          axios.get(`${API}/health/api`),
        ]);
        if (cancelled) return;
        setCoverage(cov.data);
        setFreshness(fresh.data);
        setApiStatus(health.data);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e.message || "Could not reach the predictor service");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    const timer = setInterval(load, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const card = {
    background: C.white,
    borderRadius: radius.lg,
    boxShadow: shadow.card,
    padding: "20px 22px",
  };

  if (loading) {
    return <div style={card}><span style={{ color: C.slate500 }}>Checking data sources…</span></div>;
  }

  if (error) {
    return (
      <div style={{ ...card, borderLeft: `3px solid ${C.rose}` }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Can't reach the predictor service</div>
        <div style={{ color: C.slate500, fontSize: 14 }}>
          {error}. Figures below are not being updated.
        </div>
      </div>
    );
  }

  const live = apiStatus?.status === "live";

  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Where this data comes from</h3>
        <span style={{ fontSize: 13, color: live ? C.emerald : C.amber, fontWeight: 600 }}>
          {live ? "Premier League feed connected" : "Premier League feed unavailable"}
        </span>
      </div>

      <div style={{ display: "flex", gap: 28, flexWrap: "wrap", margin: "16px 0 4px" }}>
        <Metric
          label="Season"
          value={freshness?.current_season || "—"}
          detail={`${freshness?.matches_played ?? 0} matches recorded`}
        />
        <Metric
          label="Matches with full statistics"
          value={`${coverage?.overall_coverage_pct ?? 0}%`}
          detail={`${coverage?.total_with_statistics ?? 0} of ${coverage?.total_matches ?? 0}`}
        />
        <Metric
          label="Last updated"
          value={formatWhen(freshness?.last_refreshed)}
          detail={freshness?.latest_match_date ? `latest match ${freshness.latest_match_date}` : "no matches yet"}
        />
      </div>

      <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${C.slate200}`, fontSize: 13, color: C.slate500, lineHeight: 1.6 }}>
        Results and fixtures come from the {coverage?.sources?.fixtures || "Premier League"}.
        Shots, corners, fouls and cards come from {coverage?.sources?.statistics || "football-data.co.uk"}.
        Possession and expected goals aren't published by either source, so they aren't predicted.
      </div>
    </div>
  );
}

function Metric({ label, value, detail }) {
  return (
    <div>
      <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.06em", color: C.slate400, fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: C.slate800, marginTop: 2 }}>{value}</div>
      <div style={{ fontSize: 12, color: C.slate500 }}>{detail}</div>
    </div>
  );
}

function formatWhen(iso) {
  if (!iso) return "not yet";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "not yet";
  const mins = Math.round((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  return then.toISOString().slice(0, 10);
}

import { useState, useEffect } from "react";
import axios from "axios";
import { C, radius, type, space } from "../theme";
import { API } from "../config";
import { useIsCompact } from "../hooks/useBreakpoint";

import ModelPerformanceBand from "../components/dashboard/ModelPerformanceBand";
import AccuracyTrend from "../components/dashboard/AccuracyTrend";
import SeasonComparison from "../components/dashboard/SeasonComparison";
import GoalsTrend from "../components/dashboard/GoalsTrend";
import CalibrationPanel from "../components/dashboard/CalibrationPanel";
import UpcomingFixtures from "../components/dashboard/UpcomingFixtures";
import LeagueContextPanel from "../components/dashboard/LeagueContextPanel";
import RecentPredictions from "../components/dashboard/RecentPredictions";
import DataProvenance from "../components/DataProvenance";

// Layout order follows the brief: summary before detail, and a summary you can
// read as a shape before you read it as a number.
//   1. Model performance   — is the model working? (the headline figures)
//   2. Accuracy over time  — is it *staying* working? The trend the headline
//      figures average away. Full width: it is the chart the page is for.
//   3. Season / scoring    — the same question cut two other ways
//   4. Calibration         — why should you trust the probabilities?
//   5. Upcoming fixtures    — what the model is about to be asked
//   6. League context       — secondary, describes the league not the model
//   7. Recent predictions  — the receipts
//   8. Data provenance     — integrated at the bottom as supporting context,
//      not floating above the fold as its own slab.
//
// The charts sit above the tables deliberately: a dashboard is read for the
// shape of things first, and the tables are there to answer the question the
// shape raises.
export default function Dashboard() {
  const [league, setLeague] = useState(null);
  const [leagueLoading, setLeagueLoading] = useState(true);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  // No default season string. It used to be hardcoded "2025-26", which silently
  // became last season the moment a new campaign started — the selector opened
  // on a completed season and the league panel described the wrong year.
  const [season, setSeason] = useState(null);
  const [seasons, setSeasons] = useState([]);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/seasons`)
      .then((r) => {
        if (cancelled) return;
        const list = r.data.seasons || [];
        setSeasons(list);
        if (list.length) setSeason(list[list.length - 1].id);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!season) return undefined;
    let cancelled = false;
    setLeagueLoading(true);
    axios.get(`${API}/analytics/league?season=${season}`)
      .then((r) => { if (!cancelled) setLeague(r.data); })
      .catch(() => { if (!cancelled) setLeague(null); })
      .finally(() => { if (!cancelled) setLeagueLoading(false); });
    return () => { cancelled = true; };
  }, [season]);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    axios.get(`${API}/predictions/history`)
      .then((r) => { if (!cancelled) setHistory(r.data.predictions.slice(0, 8)); })
      .catch(() => { if (!cancelled) setHistory([]); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const compact = useIsCompact();

  return (
    <div>
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: compact ? "flex-start" : "center",
        flexDirection: compact ? "column" : "row",
        gap: space.md, marginBottom: space.xl,
      }}>
        <div>
          <div style={{ ...type.page, color: C.navy }}>Dashboard</div>
          <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>Model performance first, league context second</div>
        </div>
        <select
          value={season || ""}
          onChange={(e) => setSeason(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 13, background: C.white, color: C.slate700 }}
        >
          {seasons.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>

      <div style={{ marginBottom: space.xl }}>
        <ModelPerformanceBand />
      </div>

      <div style={{ marginBottom: space.xl }}>
        <AccuracyTrend />
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: compact ? "1fr" : "1fr 1fr",
        gap: space.xl, marginBottom: space.xl, alignItems: "start",
      }}>
        <SeasonComparison />
        <GoalsTrend league={league} loading={leagueLoading} season={season} />
      </div>

      <div style={{ marginBottom: space.xl }}>
        <CalibrationPanel />
      </div>

      {/* Collapses to a single column below the lg breakpoint instead of
          squeezing two panels into a phone's width. */}
      <div style={{
        display: "grid",
        gridTemplateColumns: compact ? "1fr" : "1fr 1fr",
        gap: space.xl, marginBottom: space.xl, alignItems: "start",
      }}>
        <UpcomingFixtures />
        <LeagueContextPanel league={league} loading={leagueLoading} season={season} />
      </div>

      <div style={{ marginBottom: space.xl, overflowX: "auto" }}>
        <RecentPredictions history={history} loading={historyLoading} />
      </div>

      <DataProvenance />
    </div>
  );
}

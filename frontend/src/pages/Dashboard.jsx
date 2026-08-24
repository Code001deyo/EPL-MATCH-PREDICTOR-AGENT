import { useState, useEffect, useMemo } from "react";
import axios from "axios";
import { C, radius, type, space } from "../theme";
import { API } from "../config";
import { useIsCompact, useIsNarrow } from "../hooks/useBreakpoint";

import SummaryStrip from "../components/dashboard/SummaryStrip";
import AccuracyTrend from "../components/dashboard/AccuracyTrend";
import CalibrationPanel from "../components/dashboard/CalibrationPanel";
import SeasonComparison from "../components/dashboard/SeasonComparison";
import GoalsTrend from "../components/dashboard/GoalsTrend";
import UpcomingFixtures from "../components/dashboard/UpcomingFixtures";
import LeagueTable from "../components/dashboard/LeagueTable";
import RecentPredictions from "../components/dashboard/RecentPredictions";
import DataProvenance from "../components/DataProvenance";

/* A dashboard is read in one glance, then interrogated by scrolling.
 *
 * The previous build inverted that: the first viewport held a header, one tall
 * performance band and the top 40px of a chart, so nothing that could be compared
 * was ever on screen together. Everything below is arranged around one rule —
 * THE SUMMARY FITS ONE SCREEN, the detail lives below the fold.
 *
 * Above the fold, at 1366x768:
 *   header ~52px + summary strip ~96px + chart row ~300px  ≈ 470px
 * Below it, in descending order of "how often would someone actually need this":
 *   season comparison · scoring trend · upcoming fixtures · league table ·
 *   recent predictions · provenance
 *
 * Explanatory prose is not deleted, it is behind the ⓘ on the thing it explains.
 * The old dashboard printed it as body text and read like a report. */
export default function Dashboard() {
  const [league, setLeague] = useState(null);
  const [leagueLoading, setLeagueLoading] = useState(true);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [upcoming, setUpcoming] = useState(null);

  const [season, setSeason] = useState(null);
  const [seasons, setSeasons] = useState([]);
  const [division, setDivision] = useState("E0");
  const [divisions, setDivisions] = useState([]);

  const compact = useIsCompact();
  const narrow = useIsNarrow();

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
    axios.get(`${API}/divisions`)
      .then((r) => { if (!cancelled) setDivisions(r.data.divisions || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // League context follows BOTH selectors. This is the request that used to be the
  // only thing the season selector drove; now everything season-scoped rides on the
  // same pair of controls.
  useEffect(() => {
    // Wait for BOTH selectors. Firing before `divisions` had loaded sent
    // `division=` and the backend answered "no matches for this season and
    // division", which rendered as empty cards with no error anywhere.
    if (!season || !division) return undefined;
    let cancelled = false;
    setLeagueLoading(true);
    axios.get(`${API}/analytics/league?season=${season}&division=${division}`)
      .then((r) => { if (!cancelled) setLeague(r.data?.error ? null : r.data); })
      .catch(() => { if (!cancelled) setLeague(null); })
      .finally(() => { if (!cancelled) setLeagueLoading(false); });
    return () => { cancelled = true; };
  }, [season, division]);

  // Predictions are now season-filtered server-side rather than fetched whole and
  // sliced in the browser.
  useEffect(() => {
    if (!season) return undefined;
    let cancelled = false;
    setHistoryLoading(true);
    axios.get(`${API}/predictions/history?season=${season}&limit=8`)
      .then((r) => { if (!cancelled) setHistory(r.data.predictions || []); })
      .catch(() => { if (!cancelled) setHistory([]); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [season]);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/fixtures/upcoming`)
      .then((r) => { if (!cancelled) setUpcoming((r.data?.fixtures || []).length); })
      .catch(() => { if (!cancelled) setUpcoming(null); });
    return () => { cancelled = true; };
  }, []);

  const divisionName = useMemo(
    () => divisions.find((d) => d.id === division)?.name || "Premier League",
    [divisions, division]
  );

  return (
    <div>
      <Header
        season={season} seasons={seasons} onSeason={setSeason}
        division={division} divisions={divisions} onDivision={setDivision}
        narrow={narrow}
      />

      <div style={{ marginBottom: space.md }}>
        <SummaryStrip
          season={season} league={league} leagueLoading={leagueLoading}
          upcomingCount={upcoming} division={division}
        />
      </div>

      {/* The two charts that answer "is it working" and "can I trust it", side by
          side so they can be read together. 2:1 because the trend carries 114
          points and the calibration curve carries six. */}
      <div style={{
        display: "grid",
        gridTemplateColumns: compact ? "1fr" : "2fr 1fr",
        gap: space.md, marginBottom: space.xl, alignItems: "start",
      }}>
        <AccuracyTrend />
        <CalibrationPanel />
      </div>

      {/* ---- below the fold ---- */}

      <div style={{
        display: "grid",
        gridTemplateColumns: compact ? "1fr" : "1fr 1fr",
        gap: space.lg, marginBottom: space.lg, alignItems: "start",
      }}>
        <SeasonComparison />
        <GoalsTrend league={league} loading={leagueLoading} season={season} divisionName={divisionName} />
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: compact ? "1fr" : "1fr 1fr",
        gap: space.lg, marginBottom: space.lg, alignItems: "start",
      }}>
        <UpcomingFixtures />
        <RecentPredictions history={history} loading={historyLoading} season={season} />
      </div>

      <div style={{ marginBottom: space.lg }}>
        <LeagueTable season={season} />
      </div>

      <DataProvenance />
    </div>
  );
}

/* Compact by design: the old header spent 76px on a title and a subtitle
 * explaining the page's layout philosophy. Both selectors sit here because they
 * scope the page, and a control that scopes the page belongs at the top of it. */
function Header({ season, seasons, onSeason, division, divisions, onDivision, narrow }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between",
      alignItems: narrow ? "stretch" : "center",
      flexDirection: narrow ? "column" : "row",
      gap: space.sm, marginBottom: space.md,
    }}>
      <div style={{ ...type.title, fontSize: 20, color: C.navy }}>Dashboard</div>

      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
        <Select value={division} onChange={onDivision} ariaLabel="Division">
          {divisions.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
        <Select value={season || ""} onChange={onSeason} ariaLabel="Season">
          {seasons.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </Select>
      </div>
    </div>
  );
}

function Select({ value, onChange, children, ariaLabel }) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        padding: "6px 10px", borderRadius: radius.sm,
        border: `1px solid ${C.slate200}`, background: C.white,
        color: C.slate700, fontSize: 13, cursor: "pointer",
      }}
    >
      {children}
    </select>
  );
}

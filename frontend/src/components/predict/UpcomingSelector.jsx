import { useState, useEffect } from "react";
import axios from "axios";
import Select from "./Select";
import EmptyState from "../ui/EmptyState";
import { C, radius, space } from "../../theme";
import { API } from "../../config";

/* Pick an unplayed fixture from the live Premier League feed and predict it.
 *
 * Two defects fixed here:
 *  - the POST hardcoded season "2025-26", so once 2026-27 started every
 *    prediction was filed against the wrong season;
 *  - there was no empty state. When the feed returned nothing the component
 *    rendered two <select>s with no <option>s and a dead button, with no text
 *    explaining why. That is what "upcoming fixtures don't display" looked
 *    like from the user's side. */
export default function UpcomingSelector({ onResult }) {
  const [grouped, setGrouped] = useState({});
  const [season, setSeason] = useState(null);
  const [selectedMW, setSelectedMW] = useState("");
  const [selectedFixture, setSelectedFixture] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [feedFailed, setFeedFailed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/fixtures/upcoming`)
      .then(r => {
        if (cancelled) return;
        // The endpoint reports upstream failure in-band with HTTP 200.
        if (r.data?.error) { setFeedFailed(true); return; }
        const g = {};
        (r.data.fixtures || []).forEach(f => {
          if (!g[f.matchweek]) g[f.matchweek] = [];
          g[f.matchweek].push(f);
        });
        setGrouped(g);
        setSeason(r.data.season || null);
        const mws = Object.keys(g).map(Number).sort((a, b) => a - b);
        if (mws.length) { setSelectedMW(mws[0]); setSelectedFixture(g[mws[0]][0]); }
      })
      .catch(() => { if (!cancelled) setFeedFailed(true); })
      .finally(() => { if (!cancelled) setFetching(false); });
    return () => { cancelled = true; };
  }, []);

  const mws = Object.keys(grouped).map(Number).sort((a, b) => a - b);

  const handlePredict = async () => {
    if (!selectedFixture) return;
    setError(""); setLoading(true); onResult(null);
    try {
      const { data } = await axios.post(`${API}/predict`, {
        home_team: selectedFixture.home_team,
        away_team: selectedFixture.away_team,
        matchweek: selectedFixture.matchweek,
        // Comes from the fixture feed, so it follows the season over automatically.
        season,
      });
      onResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || "Prediction failed.");
    } finally { setLoading(false); }
  };

  if (fetching) return <EmptyState kind="loading" title="Loading fixtures…" />;

  if (feedFailed) {
    return <EmptyState kind="error" title="Could not load upcoming fixtures"
             detail="The Premier League feed did not answer. Try the 'played fixture' tab meanwhile." />;
  }

  if (mws.length === 0) {
    return <EmptyState kind="not-measured" title="No upcoming fixtures"
             detail="Every fixture in the current season has been played, or the next round is not published yet." />;
  }

  return (
    <>
      <Select label="Matchweek" value={selectedMW} onChange={e => {
        const mw = Number(e.target.value);
        setSelectedMW(mw); setSelectedFixture(grouped[mw]?.[0] || null); onResult(null);
      }}>
        {mws.map(mw => <option key={mw} value={mw}>Matchweek {mw}</option>)}
      </Select>

      <Select label="Fixture" value={selectedFixture?.pl_fixture_id || ""} onChange={e => {
        setSelectedFixture((grouped[selectedMW] || []).find(f => f.pl_fixture_id === Number(e.target.value)) || null);
        onResult(null);
      }}>
        {(grouped[selectedMW] || []).map(f => (
          <option key={f.pl_fixture_id} value={f.pl_fixture_id}>{f.home_team} vs {f.away_team}</option>
        ))}
      </Select>

      {selectedFixture && (
        <div style={{ padding: "10px 14px", background: C.slate50, borderRadius: radius.sm, marginBottom: 14, fontSize: 12, color: C.slate500 }}>
          {selectedFixture.kickoff} · <span style={{ color: C.blueDark, fontWeight: 600 }}>Upcoming</span>
          {season && <span style={{ color: C.slate400 }}> · {season}</span>}
        </div>
      )}

      {error && <p style={{ color: C.rose, fontSize: 13, marginBottom: space.sm }}>{error}</p>}

      <button onClick={handlePredict} disabled={loading || !selectedFixture}
        style={{ width: "100%", padding: 12, background: loading ? C.slate300 : C.blue, color: loading ? C.slate600 : C.navy, border: "none", borderRadius: radius.sm, fontSize: 14, fontWeight: 700, cursor: loading ? "default" : "pointer" }}>
        {loading ? "Predicting..." : "Predict Score"}
      </button>
    </>
  );
}

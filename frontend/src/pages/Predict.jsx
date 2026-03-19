import { useState, useEffect } from "react";
import axios from "axios";
import StatBar from "../components/ui/StatBar";
import Badge, { resultVariant } from "../components/ui/Badge";
import { C, shadow, radius } from "../theme";

const API = "http://localhost:8001";

const STAT_PAIRS = [
  ["home_shots", "away_shots", "Total Shots"],
  ["home_shots_ot", "away_shots_ot", "Shots on Target"],
  ["home_possession", "away_possession", "Possession", "%"],
  ["home_corners", "away_corners", "Corners"],
  ["home_fouls", "away_fouls", "Fouls"],
  ["home_yellow_cards", "away_yellow_cards", "Yellow Cards"],
];

function Card({ children, style }) {
  return <div style={{ background: C.white, borderRadius: radius.lg, boxShadow: shadow.card, padding: 24, ...style }}>{children}</div>;
}

function Select({ label, value, onChange, children, disabled }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: C.slate500, marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</label>
      <select value={value} onChange={onChange} disabled={disabled}
        style={{ width: "100%", padding: "9px 12px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`, fontSize: 14, background: C.white, color: C.slate700 }}>
        {children}
      </select>
    </div>
  );
}

function ProbBar({ label, value, color }) {
  return (
    <div style={{ flex: 1, textAlign: "center" }}>
      <div style={{ fontSize: 11, color: C.slate400, marginBottom: 5 }}>{label}</div>
      <div style={{ background: C.slate100, borderRadius: 4, height: 10, overflow: "hidden", marginBottom: 5 }}>
        <div style={{ width: `${value * 100}%`, background: color, height: "100%", transition: "width 0.5s" }} />
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color }}>{(value * 100).toFixed(1)}%</div>
    </div>
  );
}

export default function Predict() {
  const [mode, setMode] = useState("upcoming");
  const [result, setResult] = useState(null);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: C.slate800 }}>Predict</div>
        <div style={{ fontSize: 13, color: C.slate400, marginTop: 2 }}>ML-powered match score & stats prediction</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 24, alignItems: "start" }}>
        <Card>
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            {[["upcoming", "🔮 Upcoming"], ["played", "📋 Played"]].map(([k, l]) => (
              <button key={k} onClick={() => { setMode(k); setResult(null); }}
                style={{ flex: 1, padding: "9px 0", borderRadius: radius.sm, border: `1px solid ${mode === k ? C.blue : C.slate200}`,
                  background: mode === k ? C.blue : C.white, color: mode === k ? C.white : C.slate600,
                  fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                {l}
              </button>
            ))}
          </div>
          {mode === "upcoming"
            ? <UpcomingSelector onResult={setResult} />
            : <PlayedSelector onResult={setResult} />}
        </Card>

        <div>
          {result ? <PredictionResult result={result} /> : (
            <Card style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 300, color: C.slate300 }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>🔮</div>
              <div style={{ fontSize: 15, fontWeight: 500 }}>Select a fixture and click Predict</div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function UpcomingSelector({ onResult }) {
  const [grouped, setGrouped] = useState({});
  const [selectedMW, setSelectedMW] = useState("");
  const [selectedFixture, setSelectedFixture] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    axios.get(`${API}/fixtures/upcoming`).then(r => {
      const g = {};
      (r.data.fixtures || []).forEach(f => { if (!g[f.matchweek]) g[f.matchweek] = []; g[f.matchweek].push(f); });
      setGrouped(g);
      const mws = Object.keys(g).map(Number).sort((a, b) => a - b);
      if (mws.length) { setSelectedMW(mws[0]); setSelectedFixture(g[mws[0]][0]); }
    }).catch(() => setError("Could not load upcoming fixtures.")).finally(() => setFetching(false));
  }, []);

  const mws = Object.keys(grouped).map(Number).sort((a, b) => a - b);

  const handlePredict = async () => {
    if (!selectedFixture) return;
    setError(""); setLoading(true); onResult(null);
    try {
      const { data } = await axios.post(`${API}/predict`, { home_team: selectedFixture.home_team, away_team: selectedFixture.away_team, matchweek: selectedFixture.matchweek, season: "2025-26" });
      onResult(data);
    } catch (e) { setError(e.response?.data?.detail || "Prediction failed."); }
    finally { setLoading(false); }
  };

  if (fetching) return <p style={{ color: C.slate400, fontSize: 13 }}>Loading fixtures...</p>;

  return (
    <>
      <Select label="Matchweek" value={selectedMW} onChange={e => { const mw = Number(e.target.value); setSelectedMW(mw); setSelectedFixture(grouped[mw]?.[0] || null); onResult(null); }}>
        {mws.map(mw => <option key={mw} value={mw}>Matchweek {mw}</option>)}
      </Select>
      <Select label="Fixture" value={selectedFixture?.pl_fixture_id || ""} onChange={e => { setSelectedFixture((grouped[selectedMW] || []).find(f => f.pl_fixture_id === Number(e.target.value)) || null); onResult(null); }}>
        {(grouped[selectedMW] || []).map(f => <option key={f.pl_fixture_id} value={f.pl_fixture_id}>{f.home_team} vs {f.away_team}</option>)}
      </Select>
      {selectedFixture && (
        <div style={{ padding: "10px 14px", background: C.slate50, borderRadius: radius.sm, marginBottom: 14, fontSize: 12, color: C.slate500 }}>
          📅 {selectedFixture.kickoff} · <span style={{ color: C.blue, fontWeight: 600 }}>Upcoming</span>
        </div>
      )}
      {error && <p style={{ color: C.rose, fontSize: 13, marginBottom: 8 }}>{error}</p>}
      <button onClick={handlePredict} disabled={loading || !selectedFixture}
        style={{ width: "100%", padding: 12, background: loading ? C.slate300 : C.blue, color: C.white, border: "none", borderRadius: radius.sm, fontSize: 14, fontWeight: 700, cursor: loading ? "default" : "pointer" }}>
        {loading ? "Predicting..." : "Predict Score"}
      </button>
    </>
  );
}

function PlayedSelector({ onResult }) {
  const [seasons, setSeasons] = useState([]);
  const [selectedSeason, setSelectedSeason] = useState("");
  const [fixtures, setFixtures] = useState([]);
  const [matchweeks, setMatchweeks] = useState([]);
  const [selectedMW, setSelectedMW] = useState("");
  const [mwFixtures, setMwFixtures] = useState([]);
  const [selectedFixture, setSelectedFixture] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    axios.get(`${API}/seasons`).then(r => { const s = [...r.data.seasons].reverse(); setSeasons(s); if (s.length) setSelectedSeason(s[0].id); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedSeason) return;
    setFixtures([]); setMatchweeks([]); setSelectedMW(""); setMwFixtures([]); setSelectedFixture(null); onResult(null);
    axios.get(`${API}/fixtures/season/${encodeURIComponent(selectedSeason)}`).then(r => {
      const fx = r.data.fixtures;
      setFixtures(fx);
      const mws = [...new Set(fx.map(f => f.matchweek))].sort((a, b) => a - b);
      setMatchweeks(mws);
      if (mws.length) setSelectedMW(mws[mws.length - 1]);
    }).catch(() => {});
  }, [selectedSeason]);

  useEffect(() => {
    if (!selectedMW) return;
    const filtered = fixtures.filter(f => f.matchweek === Number(selectedMW));
    setMwFixtures(filtered); setSelectedFixture(filtered[0] || null); onResult(null);
  }, [selectedMW, fixtures]);

  const handlePredict = async () => {
    if (!selectedFixture) return;
    setError(""); setLoading(true); onResult(null);
    try {
      const { data } = await axios.post(`${API}/predict`, { fixture_id: selectedFixture.id });
      onResult(data);
    } catch (e) { setError(e.response?.data?.detail || "Prediction failed."); }
    finally { setLoading(false); }
  };

  return (
    <>
      <Select label="Season" value={selectedSeason} onChange={e => setSelectedSeason(e.target.value)}>
        {seasons.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
      </Select>
      <Select label="Matchweek" value={selectedMW} onChange={e => setSelectedMW(e.target.value)} disabled={!matchweeks.length}>
        {matchweeks.map(mw => <option key={mw} value={mw}>Matchweek {mw}</option>)}
      </Select>
      <Select label="Fixture" value={selectedFixture?.id || ""} onChange={e => { setSelectedFixture(mwFixtures.find(f => f.id === Number(e.target.value)) || null); onResult(null); }} disabled={!mwFixtures.length}>
        {mwFixtures.map(f => <option key={f.id} value={f.id}>{f.home_team} vs {f.away_team}</option>)}
      </Select>
      {selectedFixture && (
        <div style={{ padding: "10px 14px", background: C.slate50, borderRadius: radius.sm, marginBottom: 14, fontSize: 12, color: C.slate500 }}>
          📅 {selectedFixture.date} · Actual: <strong style={{ color: C.slate700 }}>{selectedFixture.score}</strong>
        </div>
      )}
      {error && <p style={{ color: C.rose, fontSize: 13, marginBottom: 8 }}>{error}</p>}
      <button onClick={handlePredict} disabled={loading || !selectedFixture}
        style={{ width: "100%", padding: 12, background: loading ? C.slate300 : C.blue, color: C.white, border: "none", borderRadius: radius.sm, fontSize: 14, fontWeight: 700, cursor: loading ? "default" : "pointer" }}>
        {loading ? "Predicting..." : "Predict Score"}
      </button>
    </>
  );
}

function PredictionResult({ result }) {
  const variant = resultVariant(result.predicted_score, result.actual_score);
  const stats = result.predicted_stats || {};
  const [homeTeam, awayTeam] = result.fixture.split(" vs ");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Card>
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <div style={{ fontSize: 12, color: C.slate400, marginBottom: 4 }}>{result.fixture} · MW{result.matchweek} · {result.season}</div>
          {result.date && <div style={{ fontSize: 11, color: C.slate300 }}>📅 {result.date}</div>}
        </div>

        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 32, marginBottom: 16 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 11, color: C.slate400, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>{homeTeam}</div>
            <div style={{ fontSize: 56, fontWeight: 800, color: C.blue, lineHeight: 1 }}>{result.home_goals}</div>
            <div style={{ fontSize: 11, color: C.slate400, marginTop: 4 }}>Predicted</div>
          </div>
          <div style={{ fontSize: 28, color: C.slate300, fontWeight: 300 }}>—</div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 11, color: C.slate400, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.06em" }}>{awayTeam}</div>
            <div style={{ fontSize: 56, fontWeight: 800, color: C.rose, lineHeight: 1 }}>{result.away_goals}</div>
            <div style={{ fontSize: 11, color: C.slate400, marginTop: 4 }}>Predicted</div>
          </div>
        </div>

        {result.actual_score && (
          <div style={{ textAlign: "center", marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: C.slate500 }}>Actual: <strong style={{ color: C.slate800 }}>{result.actual_score}</strong></div>
            <div style={{ marginTop: 8 }}><Badge variant={variant} /></div>
          </div>
        )}

        <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
          <ProbBar label="Home Win" value={result.probabilities.home_win} color={C.blue} />
          <ProbBar label="Draw" value={result.probabilities.draw} color={C.amber} />
          <ProbBar label="Away Win" value={result.probabilities.away_win} color={C.rose} />
        </div>

        <div style={{ textAlign: "center", fontSize: 12, color: C.slate400 }}>
          Model confidence: <strong style={{ color: C.slate600 }}>{(result.confidence * 100).toFixed(0)}%</strong>
        </div>

        {result.key_drivers?.length > 0 && (
          <div style={{ marginTop: 14, padding: "10px 14px", background: C.slate50, borderRadius: radius.sm }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.slate500, marginBottom: 6, textTransform: "uppercase" }}>Key Drivers</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {result.key_drivers.map((d, i) => (
                <span key={i} style={{ background: C.white, border: `1px solid ${C.slate200}`, borderRadius: 20, padding: "3px 10px", fontSize: 11, color: C.slate600 }}>{d}</span>
              ))}
            </div>
          </div>
        )}
      </Card>

      {Object.keys(stats).length > 0 && (
        <Card>
          <div style={{ fontSize: 15, fontWeight: 700, color: C.slate800, marginBottom: 4 }}>📊 Predicted Match Stats</div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700, color: C.slate400, marginBottom: 16, textTransform: "uppercase" }}>
            <span style={{ color: C.blue }}>{homeTeam}</span>
            <span>Stat</span>
            <span style={{ color: C.rose }}>{awayTeam}</span>
          </div>
          {STAT_PAIRS.map(([hk, ak, label, unit = ""]) => (
            stats[hk] !== undefined && <StatBar key={label} label={label} home={stats[hk]} away={stats[ak]} unit={unit} />
          ))}
        </Card>
      )}
    </div>
  );
}

import React, { useState, useEffect } from "react";
import axios from "axios";

const API = "http://localhost:8001";

const MODES = ["Upcoming Fixtures", "Played Fixtures"];

export default function PredictionCard() {
  const [mode, setMode] = useState("Upcoming Fixtures");

  return (
    <div style={styles.card}>
      <h2 style={styles.title}>⚽ EPL Score Predictor</h2>

      <div style={styles.modeRow}>
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{ ...styles.modeBtn, ...(mode === m ? styles.modeBtnActive : {}) }}
          >
            {m === "Upcoming Fixtures" ? "🔮 " : "📋 "}{m}
          </button>
        ))}
      </div>

      {mode === "Upcoming Fixtures" ? <UpcomingPredictor /> : <PlayedPredictor />}
    </div>
  );
}

// ── Upcoming fixtures: predict future games ──────────────────────────────────
function UpcomingPredictor() {
  const [fixtures, setFixtures] = useState([]);
  const [grouped, setGrouped] = useState({});
  const [selectedMW, setSelectedMW] = useState("");
  const [selectedFixture, setSelectedFixture] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setFetching(true);
    axios.get(`${API}/fixtures/upcoming`).then((r) => {
      const fx = r.data.fixtures || [];
      setFixtures(fx);
      const g = {};
      fx.forEach((f) => {
        if (!g[f.matchweek]) g[f.matchweek] = [];
        g[f.matchweek].push(f);
      });
      setGrouped(g);
      const mws = Object.keys(g).map(Number).sort((a, b) => a - b);
      if (mws.length) {
        setSelectedMW(mws[0]);
        setSelectedFixture(g[mws[0]][0]);
      }
    }).catch(() => setError("Could not load upcoming fixtures."))
      .finally(() => setFetching(false));
  }, []);

  const handlePredict = async () => {
    if (!selectedFixture) return;
    setError(""); setLoading(true); setResult(null);
    try {
      const { data } = await axios.post(`${API}/predict`, {
        home_team: selectedFixture.home_team,
        away_team: selectedFixture.away_team,
        matchweek: selectedFixture.matchweek,
        season: "2025-26",
        kickoff: selectedFixture.kickoff,
      });
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || "Prediction failed.");
    } finally {
      setLoading(false);
    }
  };

  const mws = Object.keys(grouped).map(Number).sort((a, b) => a - b);

  if (fetching) return <p style={styles.info}>Loading upcoming fixtures from Premier League...</p>;
  if (!fixtures.length) return <p style={styles.info}>No upcoming fixtures found.</p>;

  return (
    <>
      <div style={styles.field}>
        <label style={styles.label}>Matchweek</label>
        <select value={selectedMW} onChange={(e) => {
          const mw = Number(e.target.value);
          setSelectedMW(mw);
          setSelectedFixture(grouped[mw]?.[0] || null);
          setResult(null);
        }} style={styles.select}>
          {mws.map((mw) => <option key={mw} value={mw}>Matchweek {mw}</option>)}
        </select>
      </div>

      <div style={styles.field}>
        <label style={styles.label}>Fixture</label>
        <select
          value={selectedFixture?.pl_fixture_id || ""}
          onChange={(e) => {
            const fx = (grouped[selectedMW] || []).find((f) => f.pl_fixture_id === Number(e.target.value));
            setSelectedFixture(fx || null);
            setResult(null);
          }}
          style={styles.select}
        >
          {(grouped[selectedMW] || []).map((f) => (
            <option key={f.pl_fixture_id} value={f.pl_fixture_id}>
              {f.home_team} vs {f.away_team}
            </option>
          ))}
        </select>
      </div>

      {selectedFixture && (
        <div style={styles.fixtureInfo}>
          <span style={styles.fixtureDate}>📅 {selectedFixture.kickoff}</span>
          <span style={{ ...styles.badge, background: "#ebf8ff", color: "#2b6cb0" }}>Upcoming</span>
        </div>
      )}

      {error && <p style={styles.error}>{error}</p>}
      <button onClick={handlePredict} disabled={loading || !selectedFixture} style={styles.button}>
        {loading ? "Predicting..." : "Predict Score"}
      </button>

      {result && <PredictionResult result={result} />}
    </>
  );
}

// ── Played fixtures: backtest against known results ──────────────────────────
function PlayedPredictor() {
  const [seasons, setSeasons] = useState([]);
  const [selectedSeason, setSelectedSeason] = useState("");
  const [fixtures, setFixtures] = useState([]);
  const [matchweeks, setMatchweeks] = useState([]);
  const [selectedMW, setSelectedMW] = useState("");
  const [mwFixtures, setMwFixtures] = useState([]);
  const [selectedFixture, setSelectedFixture] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    axios.get(`${API}/seasons`).then((r) => {
      const s = [...r.data.seasons].reverse();
      setSeasons(s);
      if (s.length) setSelectedSeason(s[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedSeason) return;
    setFixtures([]); setMatchweeks([]); setSelectedMW(""); setMwFixtures([]); setSelectedFixture(null); setResult(null);
    axios.get(`${API}/fixtures/season/${encodeURIComponent(selectedSeason)}`).then((r) => {
      const fx = r.data.fixtures;
      setFixtures(fx);
      const mws = [...new Set(fx.map((f) => f.matchweek))].sort((a, b) => a - b);
      setMatchweeks(mws);
      if (mws.length) setSelectedMW(mws[mws.length - 1]);
    }).catch(() => {});
  }, [selectedSeason]);

  useEffect(() => {
    if (!selectedMW) return;
    const filtered = fixtures.filter((f) => f.matchweek === Number(selectedMW));
    setMwFixtures(filtered);
    setSelectedFixture(filtered[0] || null);
    setResult(null);
  }, [selectedMW, fixtures]);

  const handlePredict = async () => {
    if (!selectedFixture) { setError("Select a fixture."); return; }
    setError(""); setLoading(true);
    try {
      const { data } = await axios.post(`${API}/predict`, { fixture_id: selectedFixture.id });
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || "Prediction failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div style={styles.field}>
        <label style={styles.label}>Season</label>
        <select value={selectedSeason} onChange={(e) => setSelectedSeason(e.target.value)} style={styles.select}>
          {seasons.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>

      <div style={styles.field}>
        <label style={styles.label}>Matchweek</label>
        <select value={selectedMW} onChange={(e) => setSelectedMW(e.target.value)} style={styles.select} disabled={!matchweeks.length}>
          {matchweeks.map((mw) => <option key={mw} value={mw}>Matchweek {mw}</option>)}
        </select>
      </div>

      <div style={styles.field}>
        <label style={styles.label}>Fixture</label>
        <select
          value={selectedFixture?.id || ""}
          onChange={(e) => {
            setSelectedFixture(mwFixtures.find((f) => f.id === Number(e.target.value)) || null);
            setResult(null);
          }}
          style={styles.select}
          disabled={!mwFixtures.length}
        >
          {mwFixtures.map((f) => (
            <option key={f.id} value={f.id}>{f.home_team} vs {f.away_team}</option>
          ))}
        </select>
      </div>

      {selectedFixture && (
        <div style={styles.fixtureInfo}>
          <span style={styles.fixtureDate}>📅 {selectedFixture.date}</span>
          <span style={styles.fixtureScore}>Actual: <strong>{selectedFixture.score}</strong></span>
        </div>
      )}

      {error && <p style={styles.error}>{error}</p>}
      <button onClick={handlePredict} disabled={loading || !selectedFixture} style={styles.button}>
        {loading ? "Predicting..." : "Predict Score"}
      </button>

      {result && <PredictionResult result={result} />}
    </>
  );
}

// ── Shared result display ─────────────────────────────────────────────────────
function PredictionResult({ result }) {
  const correct = result.actual_score && result.actual_score === result.predicted_score;
  const resultCorrect = result.actual_score && (() => {
    const [ph, pa] = result.predicted_score.split("-").map(Number);
    const [ah, aa] = result.actual_score.split("-").map(Number);
    const pr = ph > pa ? "H" : ph === pa ? "D" : "A";
    const ar = ah > aa ? "H" : ah === aa ? "D" : "A";
    return pr === ar;
  })();

  return (
    <div style={styles.result}>
      <p style={styles.fixtureName}>{result.fixture} · MW{result.matchweek} · {result.season}</p>
      {result.date && <p style={styles.kickoffLabel}>📅 {result.date}</p>}

      <div style={styles.scoreRow}>
        <div style={styles.scoreBox}>
          <div style={styles.scoreLabel}>Predicted</div>
          <div style={styles.scoreValue}>{result.predicted_score}</div>
        </div>
        {result.actual_score && (
          <div style={styles.scoreBox}>
            <div style={styles.scoreLabel}>Actual</div>
            <div style={{ ...styles.scoreValue, color: correct ? "#38a169" : resultCorrect ? "#d69e2e" : "#e53e3e" }}>
              {result.actual_score}
            </div>
          </div>
        )}
      </div>

      {result.actual_score && (
        <p style={{ textAlign: "center", fontSize: 12, color: "#718096", marginBottom: 12 }}>
          {correct ? "✅ Correct score" : resultCorrect ? "🟡 Correct result" : "❌ Wrong result"}
        </p>
      )}

      <div style={styles.probRow}>
        <ProbBar label="Home Win" value={result.probabilities.home_win} color="#3182ce" />
        <ProbBar label="Draw" value={result.probabilities.draw} color="#d69e2e" />
        <ProbBar label="Away Win" value={result.probabilities.away_win} color="#e53e3e" />
      </div>

      <p style={styles.confidence}>Model confidence: {(result.confidence * 100).toFixed(0)}%</p>

      {result.key_drivers?.length > 0 && (
        <div style={styles.drivers}>
          <strong>Key drivers:</strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {result.key_drivers.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function ProbBar({ label, value, color }) {
  return (
    <div style={{ flex: 1, textAlign: "center" }}>
      <div style={{ fontSize: 11, marginBottom: 4, color: "#718096" }}>{label}</div>
      <div style={{ background: "#eee", borderRadius: 4, height: 10, overflow: "hidden" }}>
        <div style={{ width: `${value * 100}%`, background: color, height: "100%", transition: "width 0.4s" }} />
      </div>
      <div style={{ fontSize: 13, marginTop: 4, fontWeight: 600 }}>{(value * 100).toFixed(1)}%</div>
    </div>
  );
}

const styles = {
  card: { maxWidth: 580, margin: "40px auto", padding: 32, borderRadius: 12, boxShadow: "0 4px 24px rgba(0,0,0,0.1)", fontFamily: "sans-serif", background: "#fff" },
  title: { textAlign: "center", marginBottom: 16, color: "#1a202c", fontSize: 22 },
  modeRow: { display: "flex", gap: 8, marginBottom: 20 },
  modeBtn: { flex: 1, padding: "9px 0", borderRadius: 8, border: "1px solid #cbd5e0", background: "#f7fafc", color: "#4a5568", fontSize: 13, cursor: "pointer", fontWeight: 500 },
  modeBtnActive: { background: "#2b6cb0", color: "#fff", border: "1px solid #2b6cb0" },
  field: { marginBottom: 14 },
  label: { display: "block", fontSize: 11, fontWeight: 700, color: "#4a5568", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" },
  select: { width: "100%", padding: "9px 12px", borderRadius: 6, border: "1px solid #cbd5e0", fontSize: 14, background: "#fff" },
  fixtureInfo: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "#f7fafc", borderRadius: 6, marginBottom: 14, fontSize: 13 },
  fixtureDate: { color: "#718096" },
  fixtureScore: { color: "#2d3748" },
  badge: { padding: "2px 10px", borderRadius: 12, fontSize: 12, fontWeight: 600 },
  button: { width: "100%", padding: "12px", background: "#2b6cb0", color: "#fff", border: "none", borderRadius: 8, fontSize: 15, cursor: "pointer", marginTop: 4, fontWeight: 600 },
  error: { color: "#e53e3e", fontSize: 13, marginBottom: 8 },
  info: { color: "#718096", textAlign: "center", padding: "20px 0" },
  result: { marginTop: 20, padding: 20, background: "#f7fafc", borderRadius: 10 },
  fixtureName: { textAlign: "center", color: "#718096", fontSize: 13, marginBottom: 4 },
  kickoffLabel: { textAlign: "center", color: "#a0aec0", fontSize: 12, marginBottom: 12 },
  scoreRow: { display: "flex", justifyContent: "center", gap: 32, marginBottom: 8 },
  scoreBox: { textAlign: "center" },
  scoreLabel: { fontSize: 11, color: "#718096", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 },
  scoreValue: { fontSize: 42, fontWeight: "bold", color: "#1a202c", lineHeight: 1 },
  probRow: { display: "flex", gap: 12, marginBottom: 12 },
  confidence: { textAlign: "center", color: "#718096", fontSize: 13 },
  drivers: { fontSize: 12, color: "#4a5568", marginTop: 8 },
};

import React, { useState, useEffect } from "react";
import axios from "axios";
import PredictionCard from "./components/PredictionCard";
import TeamStats from "./components/TeamStats";
import HistoryTable from "./components/HistoryTable";

const API = "http://localhost:8001";
const TABS = ["Predict", "Team Stats", "History"];

export default function App() {
  const [tab, setTab] = useState("Predict");
  const [teams, setTeams] = useState([]);

  useEffect(() => {
    axios.get(`${API}/teams`).then((r) => setTeams(r.data.teams)).catch(() => {});
  }, []);

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <span style={styles.logo}>⚽ EPL Predictor</span>
        <nav style={styles.nav}>
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)} style={{ ...styles.navBtn, ...(tab === t ? styles.activeBtn : {}) }}>
              {t}
            </button>
          ))}
        </nav>
      </header>

      <main style={styles.main}>
        {tab === "Predict" && <PredictionCard />}
        {tab === "Team Stats" && <TeamStats teams={teams} />}
        {tab === "History" && <HistoryTable />}
      </main>
    </div>
  );
}

const styles = {
  app: { minHeight: "100vh", background: "#f0f4f8", fontFamily: "sans-serif" },
  header: { background: "#1a365d", padding: "0 32px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 60 },
  logo: { color: "#fff", fontWeight: "bold", fontSize: 20 },
  nav: { display: "flex", gap: 8 },
  navBtn: { background: "transparent", border: "none", color: "#a0aec0", fontSize: 15, cursor: "pointer", padding: "8px 16px", borderRadius: 6 },
  activeBtn: { background: "#2b6cb0", color: "#fff" },
  main: { padding: "24px 16px" },
};

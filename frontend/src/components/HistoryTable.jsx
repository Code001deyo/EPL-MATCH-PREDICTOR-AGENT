import React, { useState, useEffect } from "react";
import axios from "axios";

const API = "http://localhost:8001";

export default function HistoryTable() {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    axios.get(`${API}/predictions/history`).then((r) => setHistory(r.data.predictions)).catch(() => {});
  }, []);

  const resultColor = (pred, actual) => {
    if (!actual) return "#718096";
    const [ph, pa] = pred.split("-").map(Number);
    const [ah, aa] = actual.split("-").map(Number);
    if (ph === ah && pa === aa) return "#38a169";
    const pr = ph > pa ? "H" : ph === pa ? "D" : "A";
    const ar = ah > aa ? "H" : ah === aa ? "D" : "A";
    return pr === ar ? "#d69e2e" : "#e53e3e";
  };

  return (
    <div style={styles.container}>
      <h3>Prediction History</h3>
      {history.length === 0 ? (
        <p style={{ color: "#718096" }}>No predictions yet.</p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr style={styles.headerRow}>
              {["Fixture", "MW", "Predicted", "Actual", "H Win%", "Draw%", "A Win%", "Conf"].map((h) => (
                <th key={h} style={styles.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history.map((p) => (
              <tr key={p.id} style={{ borderBottom: "1px solid #e2e8f0" }}>
                <td style={styles.td}>{p.fixture}</td>
                <td style={styles.td}>{p.matchweek}</td>
                <td style={{ ...styles.td, fontWeight: "bold", color: resultColor(p.predicted, p.actual) }}>{p.predicted}</td>
                <td style={styles.td}>{p.actual || "—"}</td>
                <td style={styles.td}>{(p.home_win_prob * 100).toFixed(0)}%</td>
                <td style={styles.td}>{(p.draw_prob * 100).toFixed(0)}%</td>
                <td style={styles.td}>{(p.away_win_prob * 100).toFixed(0)}%</td>
                <td style={styles.td}>{(p.confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div style={styles.legend}>
        <span style={{ color: "#38a169" }}>■ Correct score</span>&nbsp;&nbsp;
        <span style={{ color: "#d69e2e" }}>■ Correct result</span>&nbsp;&nbsp;
        <span style={{ color: "#e53e3e" }}>■ Wrong</span>
      </div>
    </div>
  );
}

const styles = {
  container: { maxWidth: 900, margin: "32px auto", padding: 24, borderRadius: 12, boxShadow: "0 4px 24px rgba(0,0,0,0.08)", fontFamily: "sans-serif" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 14 },
  headerRow: { background: "#f7fafc" },
  th: { padding: "10px 12px", textAlign: "left", fontWeight: 600, color: "#4a5568", borderBottom: "2px solid #e2e8f0" },
  td: { padding: "10px 12px", color: "#2d3748" },
  legend: { marginTop: 12, fontSize: 12, color: "#718096" },
};

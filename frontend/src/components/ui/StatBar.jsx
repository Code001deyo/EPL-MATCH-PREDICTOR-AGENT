import { C } from "../../theme";

export default function StatBar({ label, home, away, homeTeam, awayTeam, unit = "" }) {
  const total = (home || 0) + (away || 0);
  const homePct = total > 0 ? (home / total) * 100 : 50;
  const awayPct = 100 - homePct;

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 600, marginBottom: 5, color: C.slate700 }}>
        <span style={{ color: C.blue }}>{home}{unit}</span>
        <span style={{ fontSize: 11, color: C.slate400, fontWeight: 500 }}>{label}</span>
        <span style={{ color: C.rose }}>{away}{unit}</span>
      </div>
      <div style={{ display: "flex", borderRadius: 4, overflow: "hidden", height: 8 }}>
        <div style={{ width: `${homePct}%`, background: C.blue, transition: "width 0.5s" }} />
        <div style={{ width: `${awayPct}%`, background: C.rose, transition: "width 0.5s" }} />
      </div>
    </div>
  );
}

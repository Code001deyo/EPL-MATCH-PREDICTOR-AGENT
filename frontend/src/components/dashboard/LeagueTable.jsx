import { useState, useEffect } from "react";
import axios from "axios";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import EmptyState from "../ui/EmptyState";
import DataTable from "../ui/DataTable";
import { C, radius, type } from "../../theme";
import { API } from "../../config";

/* The standings, per division.
 *
 * There is a table here for each league because there are two leagues in the
 * database and only one of them was ever shown — blended into the other. The
 * league endpoint had no division filter, so a "Premier League" table listed 44
 * clubs and ranked Coventry first on 46 games played, its Championship and Premier
 * League matches summed into one row.
 *
 * The tab is not decoration: it is the control that makes the boundary visible, so
 * a reader always knows which competition a table describes. */
export default function LeagueTable({ season }) {
  const [divisions, setDivisions] = useState([]);
  const [division, setDivision] = useState("E0");
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");

  useEffect(() => {
    axios.get(`${API}/divisions`)
      .then((r) => setDivisions(r.data.divisions || []))
      .catch(() => setDivisions([{ id: "E0", name: "Premier League" }]));
  }, []);

  useEffect(() => {
    if (!season || !division) return undefined;
    let cancelled = false;
    setState("loading");
    axios.get(`${API}/analytics/league?season=${season}&division=${division}`)
      .then((r) => {
        if (cancelled) return;
        if (r.data?.error) { setState("not-measured"); setData(null); return; }
        setData(r.data);
        setState("ready");
      })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, [season, division]);

  const table = data?.form_table || [];
  // Promotion/relegation counts differ by competition, so the tint bands do too.
  const topN = division === "E0" ? 4 : 2;
  const botN = 3;

  const columns = [
    { key: "pos", header: "#", numeric: true, width: 34, render: (_r, i) => i + 1 },
    { key: "team", header: "Team", nowrap: true, minWidth: 120, render: (r) => <span style={{ fontWeight: 600, color: C.slate800 }}>{r.team}</span> },
    { key: "played", header: "P", numeric: true, width: 40 },
    { key: "won", header: "W", numeric: true, width: 40 },
    { key: "drawn", header: "D", numeric: true, width: 40 },
    { key: "lost", header: "L", numeric: true, width: 40 },
    { key: "gf", header: "GF", numeric: true, width: 44 },
    { key: "ga", header: "GA", numeric: true, width: 44 },
    { key: "gd", header: "GD", numeric: true, width: 48,
      render: (r) => <span style={{ color: r.gd > 0 ? C.emerald : r.gd < 0 ? C.rose : C.slate500, fontWeight: 600 }}>{r.gd > 0 ? `+${r.gd}` : r.gd}</span> },
    { key: "pts", header: "Pts", numeric: true, width: 46,
      render: (r) => <span style={{ fontWeight: 800, color: C.slate800 }}>{r.pts}</span> },
    { key: "last5", header: "Form", width: 130,
      render: (r) => <div style={{ display: "flex", gap: 3 }}>{(r.last5 || "").split("").map((c, j) => <FormBadge key={j} char={c} />)}</div> },
  ];

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <SectionTitle sub={data ? `${data.division_name} · ${season} · ${data.total_matches} matches played` : season}>
          League table
        </SectionTitle>
        <div style={{ display: "flex", gap: 4, marginTop: 2 }}>
          {divisions.map((d) => (
            <button key={d.id} onClick={() => setDivision(d.id)}
              style={{
                ...type.micro, padding: "5px 11px", borderRadius: radius.sm, cursor: "pointer",
                border: `1px solid ${division === d.id ? C.navy : C.slate200}`,
                background: division === d.id ? C.navy : C.white,
                color: division === d.id ? C.white : C.slate500,
              }}>
              {d.name}
            </button>
          ))}
        </div>
      </div>

      {state === "loading" && <EmptyState kind="loading" />}
      {state === "error" && <EmptyState kind="error" title="Could not load the table" />}
      {state === "not-measured" && (
        <EmptyState kind="not-measured" title="No played matches"
          detail={`No ${division === "E0" ? "Premier League" : "Championship"} matches are stored for ${season} yet.`} />
      )}

      {state === "ready" && (
        <>
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
            <DataTable
              columns={columns} rows={table} dense
              rowKey={(r) => r.team}
              rowStyle={(_r, i) =>
                i < topN ? { background: "#ece3f2" }
                : i >= table.length - botN ? { background: "#fbe3e9" }
                : null}
            />
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 16, ...type.micro, fontWeight: 400, color: C.slate400 }}>
            <span><Swatch color="#ece3f2" /> {division === "E0" ? "Champions League" : "Automatic promotion"}</span>
            <span><Swatch color="#fbe3e9" /> Relegation</span>
          </div>
        </>
      )}
    </Card>
  );
}

function Swatch({ color }) {
  // Filled and rounded: at 9px with a grey outline these read as empty
  // checkboxes rather than colour keys.
  return <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: color, border: `1px solid ${C.slate300}`, marginRight: 5, verticalAlign: "middle" }} />;
}

function FormBadge({ char }) {
  const map = {
    W: { bg: "#d9f2e6", color: C.emerald }, H: { bg: "#d9f2e6", color: C.emerald },
    D: { bg: "#fdf0d9", color: "#92400e" },
    L: { bg: "#fbe0e6", color: C.rose }, A: { bg: "#fbe0e6", color: C.rose },
  };
  const s = map[char] || { bg: C.slate100, color: C.slate400 };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 19, height: 19, borderRadius: 3, background: s.bg, color: s.color,
      fontSize: 10, fontWeight: 700,
    }}>{char}</span>
  );
}

import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import Badge, { resultVariant } from "../ui/Badge";
import EmptyState from "../ui/EmptyState";
import { C } from "../../theme";

// "Not yet played" and "wrong" must never look alike — a fixture with no
// actual score is unresolved, not a model failure. Badge already encodes
// that distinction (pending vs wrong); this panel just makes sure the
// "actual" column reads unambiguously as "hasn't happened" rather than "—"
// which is easy to misread as a missing/broken value.
export default function RecentPredictions({ history, loading }) {
  return (
    <Card>
      <SectionTitle sub="Most recent predictions, with settlement status">Recent Predictions</SectionTitle>

      {loading && <EmptyState kind="loading" title="Loading predictions…" />}

      {!loading && history.length === 0 && (
        <EmptyState kind="not-measured" title="No predictions yet" detail="Go to Predict to generate the first one." />
      )}

      {!loading && history.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: `2px solid ${C.slate100}` }}>
              {["Fixture", "Season", "MW", "Predicted", "Actual", "Status", "Confidence"].map((h) => (
                <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontWeight: 600, color: C.slate500, fontSize: 11, textTransform: "uppercase" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history.map((p) => {
              const notPlayed = !p.actual || p.actual.includes("null");
              const variant = resultVariant(p.predicted, p.actual);
              return (
                <tr key={p.id} style={{ borderBottom: `1px solid ${C.slate100}` }}>
                  <td style={{ padding: "10px 12px", fontWeight: 500, color: C.slate800 }}>{p.fixture}</td>
                  <td style={{ padding: "10px 12px", color: C.slate500 }}>{p.season}</td>
                  <td style={{ padding: "10px 12px", color: C.slate500 }}>MW{p.matchweek}</td>
                  <td style={{ padding: "10px 12px", fontWeight: 700, color: C.navy, fontSize: 15 }}>{p.predicted}</td>
                  <td style={{ padding: "10px 12px", color: notPlayed ? C.slate300 : C.slate600, fontStyle: notPlayed ? "italic" : "normal" }}>
                    {notPlayed ? "not yet played" : p.actual}
                  </td>
                  <td style={{ padding: "10px 12px" }}><Badge variant={variant} small /></td>
                  <td style={{ padding: "10px 12px", color: C.slate500 }}>
                    {Number.isFinite(p.confidence) ? `${(p.confidence * 100).toFixed(0)}%` : "not measured"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

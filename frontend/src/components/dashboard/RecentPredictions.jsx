import Card from "../ui/Card";
import Badge, { resultVariant } from "../ui/Badge";
import EmptyState from "../ui/EmptyState";
import DataTable from "../ui/DataTable";
import InfoTip from "../ui/InfoTip";
import { C, type } from "../../theme";

/* Recent predictions, with settlement status.
 *
 * "Not yet played" and "wrong" must never look alike — a fixture with no actual
 * score is unresolved, not a model failure. Badge already encodes that
 * distinction; the Actual column spells it out rather than showing a bare "—",
 * which reads as a missing or broken value.
 *
 * Now on the shared DataTable, and scoped server-side by season rather than being
 * fetched whole and sliced in the browser. */
export default function RecentPredictions({ history, loading, season }) {
  const columns = [
    { key: "fixture", header: "Fixture", nowrap: true, minWidth: 168,
      render: (p) => <span style={{ fontWeight: 600, color: C.slate800 }}>{p.fixture}</span> },
    { key: "matchweek", header: "MW", numeric: true, width: 48,
      render: (p) => <span style={{ color: C.slate500 }}>{p.matchweek}</span> },
    { key: "predicted", header: "Predicted", align: "center", width: 84,
      render: (p) => <span style={{ fontWeight: 700, color: C.navy, fontSize: 15 }}>{p.predicted}</span> },
    { key: "actual", header: "Actual", align: "center", width: 104, nowrap: true,
      render: (p) => {
        const notPlayed = !p.actual || p.actual.includes("null");
        return (
          <span style={{ color: notPlayed ? C.slate400 : C.slate700, fontStyle: notPlayed ? "italic" : "normal" }}>
            {notPlayed ? "not yet played" : p.actual}
          </span>
        );
      } },
    { key: "status", header: "Status", align: "center", width: 78,
      render: (p) => <Badge variant={resultVariant(p.predicted, p.actual)} small /> },
    { key: "confidence", header: "Conf.", numeric: true, width: 60,
      render: (p) => <span style={{ color: C.slate500 }}>
        {Number.isFinite(p.confidence) ? `${(p.confidence * 100).toFixed(0)}%` : "—"}
      </span> },
  ];

  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <span style={{ ...type.section, color: C.slate800 }}>Recent predictions</span>
        <InfoTip label="About recent predictions">
          Predictions made through the app for {season || "the selected season"}, settled
          against the real result once the fixture has been played. These are self-selected —
          whatever fixtures users happened to click — so they measure usage, not the model.
          The model's own accuracy is the holdout and backtest figures above.
        </InfoTip>
      </div>

      {loading && <EmptyState kind="loading" title="Loading predictions…" />}

      {!loading && (
        <DataTable
          columns={columns} rows={history} dense rowKey={(p) => p.id}
          empty={`No predictions for ${season || "this season"} yet — go to Predict to make one.`}
        />
      )}
    </Card>
  );
}

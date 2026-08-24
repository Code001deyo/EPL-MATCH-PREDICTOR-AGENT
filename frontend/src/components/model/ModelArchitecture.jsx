import { useState, useEffect } from "react";
import axios from "axios";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import EmptyState from "../ui/EmptyState";
import { C, radius, space, type } from "../../theme";
import { useIsCompact } from "../../hooks/useBreakpoint";
import { API } from "../../config";

/* Read from the trained artefact, never written by hand.
 *
 * This block used to be a hardcoded list claiming "35 engineered features",
 * "Home Goals + Away Goals" and an "80/20 walk-forward split". By the time it
 * was read the model had 55 features, twelve target models and a season-holdout
 * split — so the page described a model that no longer existed. Anything here
 * that can drift is now taken from /model/metrics. */
export default function ModelArchitecture() {
  const [metrics, setMetrics] = useState(null);
  const [state, setState] = useState("loading");
  const compact = useIsCompact();

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/model/metrics`)
      .then(r => {
        if (cancelled) return;
        if (!r.data?.trained) { setState("untrained"); return; }
        setMetrics(r.data);
        setState("ready");
      })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, []);

  if (state === "loading") {
    return <Card><SectionTitle>Model architecture</SectionTitle><EmptyState kind="loading" /></Card>;
  }
  if (state !== "ready") {
    return (
      <Card>
        <SectionTitle>Model architecture</SectionTitle>
        <EmptyState
          kind={state === "error" ? "error" : "not-measured"}
          title={state === "error" ? "Could not read model metrics" : "No model trained yet"}
          detail={state === "error" ? undefined : "Retrain above to populate this."}
        />
      </Card>
    );
  }

  const est = metrics.estimator || {};
  const val = metrics.validation || {};
  const acc = metrics.accuracy || {};
  const base = metrics.baselines || {};

  const statModels = Object.keys(metrics.stat_coverage || {}).length;

  const rows = [
    ["Estimator", `${est.backend || "unknown"} ${est.version || ""}`.trim()],
    ["Objective", "count:poisson"],
    ["Target models", `${statModels + 2} (goals + ${statModels} match statistics)`],
    ["Features", `${val.features ?? "—"} engineered features`],
    ["Validation", `${val.split || "—"} · ${val.train_rows ?? "—"} train / ${val.val_rows ?? "—"} holdout`],
    ["Holdout season", acc.holdout_season || "—"],
    ["Missing values", "passed through as NaN, never imputed"],
    ["Probabilities", "Poisson over the two predicted rates"],
    ["Trained at", metrics.trained_at ? new Date(metrics.trained_at).toLocaleString() : "—"],
  ];

  // Baselines the model failed to beat. Shown deliberately: metrics.json used
  // to omit the median from its verdict flags, so the page could only ever
  // report wins.
  const lost = ["home_goals", "away_goals"].flatMap(t =>
    (base[`${t}_lost_to`] || []).map(b => `${t.replace("_", " ")} loses to the ${b} baseline`)
  );

  return (
    <Card>
      <SectionTitle sub="Read from the last training run, not hardcoded.">Model architecture</SectionTitle>

      <div style={{
        display: "grid",
        gridTemplateColumns: compact ? "repeat(auto-fit, minmax(180px, 1fr))" : "repeat(3, 1fr)",
        gap: space.lg,
      }}>
        {rows.map(([k, v]) => (
          <div key={k}>
            <div style={{ ...type.label, color: C.slate600, marginBottom: 2 }}>{k}</div>
            <div style={{ ...type.body, color: C.slate500 }}>{v}</div>
          </div>
        ))}
      </div>

      {lost.length > 0 && (
        <div style={{
          marginTop: space.lg, padding: space.md, borderRadius: radius.md,
          background: C.slate50, border: `1px solid ${C.slate200}`,
        }}>
          <div style={{ ...type.label, color: C.amber, marginBottom: 4 }}>Where a trivial baseline wins</div>
          <div style={{ ...type.body, color: C.slate600 }}>{lost.join("; ")}.</div>
          <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: 6 }}>
            MAE is minimised by the median, and Premier League away goals have a median of 1, so this is
            expected — but it is reported rather than left out.
          </div>
        </div>
      )}
    </Card>
  );
}

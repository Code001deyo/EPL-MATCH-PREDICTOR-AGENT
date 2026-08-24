import { useState, useEffect } from "react";
import axios from "axios";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import Stat from "../ui/Stat";
import EmptyState from "../ui/EmptyState";
import { C, semantic } from "../../theme";
import { API } from "../../config";

// The primary content of the dashboard: "is the model working?". Reads
// /model/metrics (saved_models/metrics.json). A model at 44.7% against a
// 43.4% baseline must read as marginal — the delta bars in <Stat> collapse
// to neutral grey under a small threshold, on purpose, regardless of sign.
export default function ModelPerformanceBand() {
  const [metrics, setMetrics] = useState(null);
  const [status, setStatus] = useState("loading");
  const [holdoutSeason, setHoldoutSeason] = useState(null); // loading | not-measured | error | ready

  useEffect(() => {
    let cancelled = false;
    axios
      .get(`${API}/model/metrics`)
      .then((r) => {
        if (cancelled) return;
        setMetrics(r.data);
        const acc = r.data?.accuracy;
        setHoldoutSeason(acc?.holdout_season || null);
        const hasHoldout = r.data?.trained && acc && Number.isFinite(acc.matches_scored) && acc.matches_scored > 0;
        setStatus(hasHoldout ? "ready" : "not-measured");
      })
      .catch(() => !cancelled && setStatus("error"));
    return () => { cancelled = true; };
  }, []);

  return (
    <Card style={{ borderTop: `3px solid ${C.navy}` }}>
      <SectionTitle level="primary" sub={
        // Taken from the artefact. Hardcoding the holdout season meant the label
        // kept naming 2025-26 after the model had moved on to a newer holdout.
        holdoutSeason
          ? `Scored on the ${holdoutSeason} holdout — the most recent season the model did not train on.`
          : "Scored on the most recent season the model did not train on."
      }>
        Model Performance
      </SectionTitle>

      {status === "loading" && <EmptyState kind="loading" title="Loading model metrics…" />}

      {status === "error" && (
        <EmptyState kind="error" title="Could not reach /model/metrics" detail="The backend may be unavailable." />
      )}

      {status === "not-measured" && (
        <EmptyState
          kind="not-measured"
          title="Not yet measured"
          detail="No trained model with a scored holdout season is available yet. Retrain the model from the Model page to produce this figure."
        />
      )}

      {status === "ready" && <PopulatedBand metrics={metrics} />}
    </Card>
  );
}

function PopulatedBand({ metrics }) {
  const acc = metrics.accuracy;
  const resultDelta = round1((acc.correct_result_pct ?? NaN) - (acc.always_home_pct ?? NaN));
  const logLossDelta = round3((acc.base_rate_log_loss ?? NaN) - (acc.log_loss ?? NaN)); // positive = model beats base rate

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 32, alignItems: "start" }}>
        <Stat
          size="lg"
          label="Correct result"
          value={fmtPct(acc.correct_result_pct)}
          detail={`${acc.matches_scored} matches, ${acc.holdout_season} holdout`}
          delta={{
            label: `vs always-home baseline (${fmtPct(acc.always_home_pct)})`,
            magnitude: resultDelta,
            marginalAt: 3,
            scaleMax: 10,
          }}
        />
        <Stat
          label="Exact score"
          value={fmtPct(acc.exact_score_pct)}
          detail="low but typical for scoreline prediction"
        />
        <Stat
          label="Outcome log loss"
          value={Number.isFinite(acc.log_loss) ? acc.log_loss.toFixed(4) : "not measured"}
          detail={Number.isFinite(acc.base_rate_log_loss) ? `base-rate baseline ${acc.base_rate_log_loss.toFixed(4)} (lower is better)` : undefined}
          delta={{
            label: "improvement over base-rate log loss",
            magnitude: logLossDelta * 100, // scale into comparable points for the bar
            marginalAt: 2,
            scaleMax: 10,
          }}
        />
      </div>

      <Verdict deltaPts={resultDelta} beatsBaseline={acc.beats_always_home} />
    </div>
  );
}

function Verdict({ deltaPts, beatsBaseline }) {
  const marginal = Math.abs(deltaPts) < 3;
  const tone = marginal ? semantic.neutral : beatsBaseline ? semantic.good : semantic.bad;
  const bg = marginal ? semantic.neutralBg : beatsBaseline ? semantic.goodBg : semantic.badBg;
  const text = marginal
    ? `Beats its baseline by ${deltaPts > 0 ? "+" : ""}${deltaPts.toFixed(1)} points — real but marginal. This clears the bar of "predicts nothing" and little else.`
    : beatsBaseline
    ? `Beats its baseline by ${deltaPts.toFixed(1)} points.`
    : `Trails its baseline by ${Math.abs(deltaPts).toFixed(1)} points.`;

  return (
    <div style={{ marginTop: 20, padding: "12px 16px", background: bg, borderRadius: 8, fontSize: 13, color: tone, fontWeight: 600, lineHeight: 1.6 }}>
      {text}
    </div>
  );
}

function fmtPct(v) {
  return Number.isFinite(v) ? `${v.toFixed(1)}%` : "not measured";
}
function round1(v) { return Number.isFinite(v) ? Math.round(v * 10) / 10 : NaN; }
function round3(v) { return Number.isFinite(v) ? Math.round(v * 1000) / 1000 : NaN; }

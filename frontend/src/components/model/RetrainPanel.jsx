import { useState, useEffect, useRef } from "react";
import axios from "axios";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import { C, radius, type, space } from "../../theme";
import { API } from "../../config";

const POLL_MS = 2000;

/* Retraining is a background job, not a request.
 *
 * The button used to fire a single blocking POST with no timeout and no
 * progress. Training ran for minutes — longer than a browser will hold an idle
 * connection — so a retrain that succeeded on the server was regularly reported
 * to the user as "Retrain failed."
 *
 * The backend now answers 202 with a job id straight away. This polls it, so
 * the page can be reloaded or left mid-run without losing the job, and a
 * second click joins the run in flight instead of starting a rival that would
 * race it writing the same model files.
 *
 * The stage label matters more than it looks. Most of a retrain used to be spent
 * building the feature matrix, which reported one unchanging stage and no count,
 * so an operator watching "building feature matrix" for fifteen minutes had no
 * way to tell a working job from a wedged one. That stage now counts fixtures,
 * and the job says which unit it is counting. */
export default function RetrainPanel({ onComplete }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const timer = useRef(null);

  const running = job && job.state === "running";

  // Re-attach to a job already in flight (started by this page before a reload,
  // or from another tab) rather than showing an idle button beside a live run.
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/model/jobs`)
      .then(r => { if (!cancelled && r.data?.retrain) setJob(r.data.retrain); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!running) return undefined;
    let cancelled = false;

    const started = new Date(job.started_at).getTime();
    const tick = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);

    timer.current = setInterval(async () => {
      try {
        const { data } = await axios.get(`${API}/model/jobs/${job.id}`);
        if (cancelled) return;
        setJob(data);
        if (data.state !== "running") {
          if (data.state === "failed") setError(data.error || "Training failed.");
          else if (onComplete) onComplete();
        }
      } catch (e) {
        if (cancelled) return;
        // A polling blip is not a failed retrain — the job is server-side and
        // keeps running. Say so rather than declaring failure.
        setError("Lost contact while polling; the job may still be running.");
      }
    }, POLL_MS);

    return () => { cancelled = true; clearInterval(timer.current); clearInterval(tick); };
  }, [running, job?.id, job?.started_at, onComplete]);

  const start = async () => {
    setError(null);
    try {
      const { data } = await axios.post(`${API}/model/retrain`);
      setJob(data.job);
      if (!data.started) setError(null);
    } catch (e) {
      // 409 means the backend refused with a reason (too little data); a missing
      // response means the network failed. They are not the same problem.
      setError(e.response
        ? (e.response.data?.detail || `Rejected (HTTP ${e.response.status}).`)
        : "Could not reach the backend.");
    }
  };

  const pct = job?.total ? Math.round((job.completed / job.total) * 100) : null;
  // The job says what it is counting. This used to be hardcoded to "models",
  // which was wrong for every stage but the last: the feature build counts
  // fixtures, and it is the stage that takes the longest.
  const unit = job?.unit || "steps";

  return (
    <Card>
      <SectionTitle sub="Fits 12 models over the full match history. Runs server-side — you can leave this page.">
        Model retraining
      </SectionTitle>

      <div style={{ display: "flex", gap: space.lg, alignItems: "center", flexWrap: "wrap" }}>
        <button
          onClick={start}
          disabled={running}
          style={{
            padding: "11px 28px", border: "none", borderRadius: radius.sm,
            ...type.bodyStrong,
            background: running ? C.slate200 : C.blue,
            color: running ? C.slate600 : C.navy,
            cursor: running ? "default" : "pointer",
          }}
        >
          {running ? "Training…" : "Retrain model"}
        </button>

        {running && (
          <span style={{ ...type.label, color: C.slate500 }}>
            {job.stage}{pct !== null ? ` · ${job.completed}/${job.total} ${unit}` : ""} · {elapsed}s elapsed
          </span>
        )}
        {job && job.state === "succeeded" && (
          <span style={{ ...type.label, color: C.slate500 }}>
            Finished at {new Date(job.finished_at).toLocaleTimeString()}
            {job.result?.samples ? ` · ${job.result.samples} samples` : ""}
          </span>
        )}
      </div>

      {running && (
        <div style={{ marginTop: space.md, height: 6, background: C.slate100, borderRadius: 3, overflow: "hidden" }}>
          {/* Indeterminate while the feature matrix builds — that stage has no
              countable unit of work, and a fake percentage would be a made-up
              number in a project whose whole point is not inventing those. */}
          <div style={{
            height: "100%",
            width: pct !== null ? `${pct}%` : "100%",
            background: pct !== null ? C.blueDark : C.slate300,
            transition: "width .4s ease",
          }} />
        </div>
      )}

      {error && (
        <div style={{ marginTop: space.md, padding: space.md, borderRadius: radius.md,
                      background: "#fff5f5", border: `1px solid ${C.rose}`, ...type.body, color: C.rose }}>
          {error}
        </div>
      )}

      {job?.state === "succeeded" && job.result?.metrics && (
        <TrainingResult metrics={job.result.metrics} />
      )}
    </Card>
  );
}

function TrainingResult({ metrics }) {
  const acc = metrics.accuracy || {};
  const base = metrics.baselines || {};
  const lost = ["home_goals", "away_goals"].flatMap(t =>
    (base[`${t}_lost_to`] || []).map(b => `${t.replace("_", " ")} lost to ${b}`)
  );

  return (
    <div style={{ marginTop: space.lg, padding: space.md, background: C.slate50, borderRadius: radius.md }}>
      <div style={{ ...type.bodyStrong, color: C.slate700, marginBottom: space.sm }}>
        Holdout: {acc.holdout_season} · {acc.matches_scored} matches
      </div>
      <div style={{ display: "flex", gap: space.xl, flexWrap: "wrap", ...type.body, color: C.slate600 }}>
        <span>Correct result <strong>{acc.correct_result_pct}%</strong></span>
        <span>Exact score <strong>{acc.exact_score_pct}%</strong></span>
        <span>Log loss <strong>{acc.log_loss}</strong></span>
      </div>
      {/* The result the model lost is shown, not just the ones it won. */}
      {lost.length > 0 && (
        <div style={{ marginTop: space.sm, ...type.label, color: C.amber }}>
          Beaten by a trivial baseline: {lost.join("; ")}
        </div>
      )}
    </div>
  );
}

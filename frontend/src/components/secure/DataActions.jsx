import { useCallback, useEffect } from "react";
import axios from "axios";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import useJob from "../../hooks/useJob";
import { invalidateBacktest } from "../../hooks/useBacktest";
import { C, radius, space, type, semantic } from "../../theme";
import { API } from "../../config";

/* Refresh and backtest, both as background jobs.
 *
 * Refresh used to be a blocking POST. It downloads a season of fixtures and a
 * statistics file and then reconciles them, which on the deployed instance runs
 * past the point where the browser gives up — so the button reported "The
 * request failed." for a refresh that was still running, and the operator never
 * saw its result. Both now return a job id and are polled.
 */
export default function DataActions() {
  // Memoised so the pollers keep a stable identity across renders; an inline
  // arrow would rebuild them every render and restart the re-attach effect.
  const refreshUrl = useCallback(id => `${API}/data/jobs/${id}`, []);
  const backtestUrl = useCallback(id => `${API}/model/jobs/${id}`, []);
  const refresh = useJob(refreshUrl);
  const backtest = useJob(backtestUrl);

  // Re-join anything already in flight rather than showing idle buttons beside
  // a running job — started from another tab, or before a reload.
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/data/refresh`)
      .then(r => { if (!cancelled && r.data?.refresh) refresh.attach(r.data.refresh.id); })
      .catch(() => {});
    axios.get(`${API}/model/jobs`)
      .then(r => { if (!cancelled && r.data?.backtest) backtest.attach(r.data.backtest.id); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [refresh.attach, backtest.attach]);

  // The dashboard panels cache the backtest payload; without this they keep
  // showing the previous run until a full reload.
  const backtestState = backtest.job?.state;
  useEffect(() => {
    if (backtestState === "succeeded") invalidateBacktest();
  }, [backtestState]);

  const busy = refresh.running || backtest.running;

  return (
    <Card>
      <SectionTitle sub="Refreshing pulls newly played fixtures, re-attaches match statistics and settles any predictions those results resolve — as one operation, so statistics are never dropped part-way.">
        Data
      </SectionTitle>

      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
        <Action label="Refresh live data" busy={refresh.running} disabled={busy}
          onClick={() => refresh.start(() => axios.post(`${API}/data/refresh`))} />
        <Action label="Run backtest" busy={backtest.running} disabled={busy}
          onClick={() => backtest.start(() => axios.post(`${API}/model/backtest/run`))} />
      </div>

      <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: space.sm }}>
        A scheduled job also refreshes every 3 hours, because this instance sleeps when idle
        and its in-process timer only runs while someone is using the site.
      </div>

      <JobResult label="refresh" job={refresh.job} error={refresh.error} />
      <JobResult label="backtest" job={backtest.job} error={backtest.error} />
    </Card>
  );
}

function JobResult({ label, job, error }) {
  if (error) return <Result tone="bad">{error}</Result>;
  if (!job) return null;
  if (job.state === "running") {
    return <Result tone="good">{`${label === "refresh" ? "Refreshing" : "Backtesting"} — ${job.stage}${progressOf(job)}.`}</Result>;
  }
  if (job.state === "failed") {
    return <Result tone="bad">{`The ${label} failed: ${job.error || "no reason reported"}.`}</Result>;
  }
  return <Result tone="good">{summarise(label, job.result)}</Result>;
}

function progressOf(job) {
  return job.total ? ` (${job.completed}/${job.total} ${job.unit || "steps"})` : "";
}

function summarise(label, result) {
  if (label === "refresh") {
    if (result?.status === "season-not-published") {
      return "The new season is not published by the feed yet — nothing to refresh. This is the expected pre-season answer, not a failure.";
    }
    return `Refreshed ${result?.played_fixtures ?? 0} played fixtures, attached statistics to ${result?.statistics_attached ?? 0}, settled ${result?.predictions_settled ?? 0} prediction(s).`;
  }
  // Reported from the run's own summary rather than "it started": the numbers
  // are the point of running it.
  const h = result?.headline || {};
  return `Backtest complete — ${result?.matches_scored ?? 0} matches scored, `
    + `${h.correct_result_pct ?? "?"}% correct results against ${h.market_correct_pct ?? "?"}% for the bookmakers' line.`;
}

function Action({ label, onClick, busy, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: "9px 16px", borderRadius: radius.sm, border: `1px solid ${C.navy}`,
      background: disabled ? C.slate100 : C.navy, color: disabled ? C.slate400 : C.white,
      ...type.bodyStrong, cursor: disabled ? "default" : "pointer",
    }}>
      {busy ? "Working…" : label}
    </button>
  );
}

function Result({ tone, children }) {
  const t = tone === "good"
    ? { fg: semantic.good, bg: semantic.goodBg, border: semantic.goodBorder }
    : { fg: semantic.bad, bg: semantic.badBg, border: semantic.badBorder };
  return (
    <div style={{
      marginTop: space.md, padding: "10px 12px", borderRadius: radius.sm,
      background: t.bg, border: `1px solid ${t.border}`, color: t.fg, ...type.body,
    }}>
      {children}
    </div>
  );
}

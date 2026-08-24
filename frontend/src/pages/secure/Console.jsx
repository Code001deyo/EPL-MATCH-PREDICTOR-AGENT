import { useState } from "react";
import axios from "axios";
import Card from "../../components/ui/Card";
import SectionTitle from "../../components/ui/SectionTitle";
import RetrainPanel from "../../components/model/RetrainPanel";
import SecurityCard from "../../components/secure/SecurityCard";
import DataProvenance from "../../components/DataProvenance";
import useAuth from "../../hooks/useAuth";
import { invalidateBacktest } from "../../hooks/useBacktest";
import { C, radius, space, type, semantic } from "../../theme";
import { API } from "../../config";

/* Operator controls, separated from the public site.
 *
 * Everything here changes the model or the data, which is why it is behind a
 * login: an open retrain button is a denial-of-service control on a 0.1 vCPU
 * instance, and an open refresh is a way to churn the database.
 *
 * The public Model page keeps the metrics, calibration and baselines — those are
 * the numbers that let a visitor judge the model, and hiding them would make the
 * app less honest, not more secure. */
export default function Console() {
  const { username, logout } = useAuth();

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: space.sm, marginBottom: space.lg }}>
        <div>
          <div style={{ ...type.page, color: C.navy }}>Model operations</div>
          <div style={{ ...type.body, color: C.slate500 }}>
            Signed in as <strong>{username}</strong>
          </div>
        </div>
        <button onClick={logout} style={{
          padding: "7px 14px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`,
          background: C.white, color: C.slate600, ...type.label, cursor: "pointer",
        }}>
          Sign out
        </button>
      </div>

      <div style={{ marginBottom: space.lg }}>
        <RetrainPanel />
      </div>

      <div style={{ marginBottom: space.lg }}>
        <DataActions />
      </div>

      <div style={{ marginBottom: space.lg }}>
        <SecurityCard />
      </div>

      <DataProvenance />
    </div>
  );
}

function DataActions() {
  const [state, setState] = useState({ kind: "idle" });

  const run = async (label, request) => {
    setState({ kind: "busy", label });
    try {
      const r = await request();
      setState({ kind: "done", label, data: r.data });
    } catch (err) {
      setState({
        kind: "error", label,
        message: err?.response?.status === 401
          ? "Your session expired — sign in again."
          : err?.response?.data?.detail || "The request failed.",
      });
    }
  };

  const busy = state.kind === "busy";

  return (
    <Card>
      <SectionTitle sub="Refreshing pulls newly played fixtures, re-attaches match statistics and settles any predictions those results resolve — as one operation, so statistics are never dropped part-way.">
        Data
      </SectionTitle>

      <div style={{ display: "flex", gap: space.sm, flexWrap: "wrap" }}>
        <Action label="Refresh live data" busy={busy && state.label === "refresh"} disabled={busy}
          onClick={() => run("refresh", () => axios.post(`${API}/data/refresh`))} />
        <Action label="Run backtest" busy={busy && state.label === "backtest"} disabled={busy}
          onClick={() => run("backtest", async () => {
            const r = await axios.post(`${API}/model/backtest/run`);
            // The dashboard panels cache the backtest payload; without this they
            // keep showing the previous run until a full reload.
            invalidateBacktest();
            return r;
          })} />
      </div>

      <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: space.sm }}>
        A scheduled job also refreshes every 3 hours, because this instance sleeps when idle
        and its in-process timer only runs while someone is using the site.
      </div>

      {state.kind === "done" && (
        <Result tone="good">{summarise(state.label, state.data)}</Result>
      )}
      {state.kind === "error" && <Result tone="bad">{state.message}</Result>}
    </Card>
  );
}

function summarise(label, data) {
  if (label === "refresh") {
    if (data?.status === "season-not-published") {
      return "The new season is not published by the feed yet — nothing to refresh. This is the expected pre-season answer, not a failure.";
    }
    return `Refreshed ${data?.played_fixtures ?? 0} played fixtures, attached statistics to ${data?.statistics_attached ?? 0}, settled ${data?.predictions_settled ?? 0} prediction(s).`;
  }
  return `Backtest started (job ${data?.job_id ?? "?"}). It runs in the background; the dashboard updates when it finishes.`;
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

import { useState, useEffect } from "react";
import axios from "axios";
import MetricCard from "../ui/MetricCard";
import { C } from "../../theme";
import useBacktest from "../../hooks/useBacktest";
import { API } from "../../config";

/* The one-row summary the dashboard opens with.
 *
 * This replaces ModelPerformanceBand, which occupied ~290px on its own — a card
 * title, a subtitle, three large stats with delta bars and a verdict paragraph —
 * so nothing else fitted above the fold. Same numbers, one row, with the verdict
 * sentence moved into the ⓘ on the metric it describes.
 *
 * Six cards: three about the model, three about the selected season. That split is
 * deliberate — the top of a dashboard should answer "is it working" and "what am I
 * looking at" before anything else. */
export default function SummaryStrip({ season, league, leagueLoading, upcomingCount, division }) {
  const [metrics, setMetrics] = useState(null);
  const [state, setState] = useState("loading");
  const { status: btStatus, data: backtest } = useBacktest();

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/model/metrics`)
      .then((r) => { if (!cancelled) { setMetrics(r.data); setState("ready"); } })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, []);

  const acc = metrics?.accuracy || {};
  const trained = state === "ready" && metrics?.trained && Number.isFinite(acc.matches_scored) && acc.matches_scored > 0;

  const resultDelta = trained ? round1(acc.correct_result_pct - acc.always_home_pct) : NaN;
  const logLossDelta = trained ? round1((acc.base_rate_log_loss - acc.log_loss) * 100) : NaN;
  const bt = btStatus === "ready" ? backtest?.headline : null;

  // A rate computed from a handful of matches is not comparable to one computed
  // from a full campaign, and rendering "78%" from nine games in the same type at
  // the same size as a 380-match figure invites exactly that comparison. Below a
  // third of a season the card says so rather than letting the number stand alone.
  // The model is trained and scored on Premier League fixtures only. With the
  // Championship selected, the three model cards would otherwise sit under a
  // "Championship" header describing a model that has never seen a Championship
  // match — so they say which competition they belong to.
  const modelScope = division && division !== "E0" ? "Premier League model" : "vs always-home";

  const played = league?.total_matches;
  const smallSample = Number.isFinite(played) && played > 0 && played < 120;
  const sampleNote = smallSample
    ? ` Only ${played} matches have been played so far, so this figure is volatile — it will move substantially as the season fills in.`
    : "";
  // "Loading" and "no backtest exists" are different states and must not render
  // the same. The card read "no backtest" for the second or two the request was in
  // flight, which is the app asserting an absence it had not yet established.
  const btLoading = btStatus === "loading";

  return (
    <div style={{
      display: "grid",
      // auto-fit with a floor rather than six fixed tracks: at 1366 it lays out as
      // one row of six, and reflows to 3x2 then 2x3 instead of overflowing.
      gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
      gap: 12, alignItems: "start",
    }}>
      <MetricCard
        label="Correct result"
        value={trained ? `${acc.correct_result_pct.toFixed(1)}%` : state === "loading" ? "…" : "—"}
        delta={trained ? { value: resultDelta, marginalAt: 3 } : undefined}
        sub={trained ? modelScope : state === "loading" ? "loading" : "not measured"}
        info={
          trained
            ? `The model is trained and scored on Premier League fixtures only, whichever division is selected above. Scored on the ${acc.holdout_season} holdout — the most recent season the model did not train on — over ${acc.matches_scored} matches. The always-home baseline calls ${acc.always_home_pct.toFixed(1)}% correct on the same fixtures, so the model's real edge is ${resultDelta > 0 ? "+" : ""}${resultDelta.toFixed(1)} points. Below about 3 points that is real but marginal: it clears the bar of "predicts nothing" and little else.`
            : "No trained model with a scored holdout season yet. Retrain from the Model page."
        }
      />

      <MetricCard
        label="Log loss"
        value={trained ? acc.log_loss.toFixed(3) : state === "loading" ? "…" : "—"}
        delta={trained ? { value: logLossDelta, suffix: "pts", marginalAt: 2 } : undefined}
        sub={trained ? "lower is better" : state === "loading" ? "loading" : "not measured"}
        info="Measures the probabilities, not just the pick — a confident wrong call is punished harder than an unsure one. Compared against the base-rate baseline, which always predicts the league's average home/draw/away split."
      />

      <MetricCard
        label="Backtested"
        value={bt ? `${bt.correct_result_pct}%` : btLoading ? "…" : "—"}
        delta={bt ? { value: round1(bt.correct_result_pct - bt.always_home_pct), marginalAt: 3 } : undefined}
        sub={bt ? `${bt.matches} matches` : btLoading ? "loading" : "no backtest yet"}
        info="A walk-forward simulation: the model is refit before each matchweek and then scored on it. Reported separately from the holdout figure because the two measure different things and averaging them would hide which is which. This figure spans the seasons the backtest was run over and does not change with the season selector."
      />

      <MetricCard
        label="Goals / game"
        value={leagueLoading ? "…" : league?.avg_goals_per_game ?? "—"}
        sub={league ? `${played} played${smallSample ? " · small sample" : ""}` : season || ""}
        accent={C.navyLight}
        info={`Average total goals per match across the selected season and division.${sampleNote}`}
      />

      <MetricCard
        label="Home win rate"
        value={leagueLoading ? "…" : league ? `${(league.home_win_rate * 100).toFixed(0)}%` : "—"}
        sub={league ? `${played} played${smallSample ? " · small sample" : ""}` : ""}
        accent={C.navyLight}
        info={`Share of matches won by the home side in the selected season and division. This is what the always-home baseline exploits.${sampleNote}`}
      />

      <MetricCard
        label="Upcoming"
        value={Number.isFinite(upcomingCount) ? upcomingCount : "—"}
        sub="fixtures scheduled"
        accent={C.navyLight}
        info="Unplayed fixtures the model can be asked to predict, from the live Premier League feed."
      />
    </div>
  );
}

function round1(v) { return Number.isFinite(v) ? Math.round(v * 10) / 10 : NaN; }

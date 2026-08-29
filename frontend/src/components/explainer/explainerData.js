/* Every figure on the explainer page, in one place.
 *
 * These are deliberately hardcoded rather than fetched, and that is worth stating
 * plainly. The page is an argument about how to *read* a football model, and its
 * numbers come from a specific measured study — a 1,140-match walk-forward
 * backtest, plus five alternative architectures trained on 1,520 matches and
 * scored on a season none of them had seen. The live endpoints do not serve the
 * alternatives, and never will: nothing in production trains a direct classifier
 * just so this page can report that it lost.
 *
 * The consequence is that these are a snapshot with a date on them, not live
 * telemetry, and the page says so where a reader can see it. If a retrain moves
 * the headline figures, `MEASURED_ON` and the numbers here are what to update —
 * the Model and Dashboard pages remain the live view.
 */

export const MEASURED_ON = "August 2026";

// Where the model sits against the only benchmark that bounds it. The market
// figure is the closing line on the same 1,140 fixtures, carried through the
// backtest so the comparison is fixture-for-fixture rather than era-against-era.
export const ACCURACY_LADDER = [
  { label: "Bookmakers' closing line", value: 54.2, note: "about as close to a ceiling as football gets", emphasis: "peer" },
  { label: "This model", value: 53.6, note: "0.6 points behind the market", emphasis: "subject" },
  { label: "Always pick the home team", value: 43.2, note: "free, no model needed", emphasis: "baseline" },
  { label: "Random guess", value: 33.3, note: "one in three", emphasis: "baseline" },
];

// The same three seasons, separated. The point of this table is that the model
// and the market rise and fall *together* — a season is a much larger effect
// than any modelling decision, and the model's own trend in isolation is
// therefore close to meaningless.
export const BY_SEASON = [
  { season: "2023-24", model: 58.7, market: 59.7, alwaysHome: 46.1 },
  { season: "2024-25", model: 53.9, market: 53.9, alwaysHome: 40.8 },
  { season: "2025-26", model: 48.2, market: 48.9, alwaysHome: 42.6 },
];

// One full holdout season: what the model called, against what happened.
export const OUTCOME_SPLIT = [
  { outcome: "Home win", predicted: 62.4, actual: 42.6 },
  { outcome: "Draw", predicted: 0.0, actual: 27.4, note: "104 matches missed" },
  { outcome: "Away win", predicted: 37.6, actual: 30.0 },
];

// The five alternatives, scored on the same holdout season. Ordered worst-to-best
// by RPS is tempting and wrong: the shipped approach goes first because the page
// is asking "should this change?", and the answer is read against the incumbent.
export const ALTERNATIVES = [
  { name: "Predict goals, then derive the result", correct: 48.7, logLoss: 1.0375, rps: 0.2119, draws: 0, current: true },
  { name: "Same, with the probabilities re-tuned", correct: 47.4, logLoss: 1.06, rps: 0.2185, draws: 0 },
  { name: "Blend of both approaches", correct: 47.6, logLoss: 1.0464, rps: 0.2141, draws: 0 },
  { name: "Predict the result directly", correct: 46.1, logLoss: 1.1405, rps: 0.2335, draws: 14 },
  { name: "Predict the result, more cautiously", correct: 45.8, logLoss: 1.0872, rps: 0.2237, draws: 4 },
  { name: "Just guess the league averages", correct: 42.6, logLoss: 1.0845, rps: 0.2278, draws: 0 },
];

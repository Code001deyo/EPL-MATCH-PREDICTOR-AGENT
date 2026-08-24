import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { ComposedChart, Line, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import EmptyState from "../ui/EmptyState";
import { C } from "../../theme";
import { series, axis, grid, tooltipStyle } from "../charts/chartTheme";
import { invalidateBacktest } from "../../hooks/useBacktest";
import { API } from "../../config";

const DIAGONAL = [{ x: 0, y: 0 }, { x: 1, y: 1 }];

// Predicted probability bucket vs observed frequency, with the diagonal
// drawn. This depends on GET /model/backtest, which a concurrent engineer is
// building — it may 404. That is not an error state to hide; it is the
// honest current state of "calibration has not been measured yet."
export default function CalibrationPanel() {
  const [status, setStatus] = useState("loading"); // loading | not-built | not-measured | error | ready
  const [buckets, setBuckets] = useState([]);
  const [running, setRunning] = useState(false);

  const load = useCallback(() => {
    setStatus("loading");
    axios
      .get(`${API}/model/backtest`)
      .then((r) => {
        const parsed = parseBuckets(r.data);
        if (parsed.length === 0) {
          setStatus("not-measured");
        } else {
          setBuckets(parsed);
          setStatus("ready");
        }
      })
      .catch((e) => {
        setStatus(e?.response?.status === 404 ? "not-built" : "error");
      });
  }, []);

  useEffect(() => { load(); }, [load]);

  const runBacktest = () => {
    setRunning(true);
    axios
      .post(`${API}/model/backtest/run`)
      // The accuracy trend and season comparison read the same cached payload;
      // without this they would keep rendering the previous run until a reload.
      .then(() => { invalidateBacktest(); return load(); })
      .catch(() => setStatus((s) => (s === "not-built" ? "not-built" : "error")))
      .finally(() => setRunning(false));
  };

  return (
    <Card>
      <SectionTitle sub="Predicted probability bucket vs observed frequency. Points on the diagonal are well-calibrated; above it the model is under-confident, below it over-confident.">
        Calibration
      </SectionTitle>

      {status === "loading" && <EmptyState kind="loading" title="Loading calibration data…" />}

      {status === "not-built" && (
        <EmptyState
          kind="not-measured"
          title="Not yet measured"
          detail="GET /model/backtest is not available on this backend yet — calibration has not been computed. This is not a zero, it is an absent measurement."
          action={
            <button onClick={runBacktest} disabled={running} style={runBtnStyle(running)}>
              {running ? "Attempting…" : "Try running a backtest"}
            </button>
          }
        />
      )}

      {status === "not-measured" && (
        <EmptyState
          kind="not-measured"
          title="Not yet measured"
          detail="The backtest endpoint responded but returned no scored buckets."
        />
      )}

      {status === "error" && (
        <EmptyState kind="error" title="Could not load calibration" detail="The backend may be unavailable." />
      )}

      {status === "ready" && <CalibrationChart buckets={buckets} />}
    </Card>
  );
}

function CalibrationChart({ buckets }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
        <CartesianGrid {...grid} vertical />
        <XAxis
          type="number" dataKey="x" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`}
          {...axis} label={{ value: "Predicted probability", position: "insideBottom", offset: -6, fontSize: 11, fill: C.slate500 }}
        />
        <YAxis
          type="number" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`}
          {...axis} label={{ value: "Observed frequency", angle: -90, position: "insideLeft", fontSize: 11, fill: C.slate500 }}
        />
        <Tooltip
          {...tooltipStyle}
          formatter={(v, name) => [`${(v * 100).toFixed(1)}%`, name]}
          labelFormatter={() => ""}
        />
        {/* Grey and dashed: the diagonal is the reference the points are read
            against, not a series competing with them. */}
        <Line data={DIAGONAL} dataKey="y" stroke={C.slate300} strokeDasharray="4 4" dot={false} name="Perfect calibration" legendType="none" />
        <Scatter data={buckets.map((b) => ({ x: b.predicted, y: b.observed, count: b.count }))}
          dataKey="y" fill={series.primary} name="Observed" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// Defensive parsing: the endpoint's real shape is not yet known (owned by a
// concurrent engineer). Accept a couple of plausible shapes; if none match,
// treat it as unmeasured rather than guessing at fields.
/* This function used to look for `data.buckets` / `data.calibration` and field
 * names like `predicted_prob` and `observed_freq`. The endpoint actually returns
 * `calibration_buckets` with `confidence_range` / `predictions` /
 * `actual_hit_rate_pct`, so none of the shapes it "defensively" accepted was the
 * real one and the panel could never render — it reported "not yet measured"
 * even against a completed 1,140-match backtest. The real shape is now handled
 * first; the rest are kept as fallbacks. */
function parseBuckets(data) {
  const raw =
    data?.calibration_buckets || data?.buckets || data?.calibration ||
    (Array.isArray(data) ? data : null);
  if (!Array.isArray(raw)) return [];
  return raw
    .map((b) => ({
      predicted: firstFinite(
        b.predicted, b.predicted_prob, b.avg_predicted, b.bucket_midpoint,
        rangeMidpoint(b.confidence_range)
      ),
      observed: firstFinite(
        b.observed, b.observed_freq, b.actual_frequency, b.observed_rate,
        asFraction(b.actual_hit_rate_pct)
      ),
      count: firstFinite(b.count, b.n, b.matches, b.predictions),
    }))
    .filter((b) => Number.isFinite(b.predicted) && Number.isFinite(b.observed));
}

// "50-60%" -> 0.55. The backend buckets by range rather than by mean predicted
// probability, so the midpoint is the honest x-position for the range.
function rangeMidpoint(range) {
  if (typeof range !== "string") return undefined;
  const nums = range.match(/\d+(?:\.\d+)?/g);
  if (!nums || nums.length < 2) return undefined;
  // The top bucket is labelled 80-101 so it can include 100%; clamp it back.
  const lo = Number(nums[0]);
  const hi = Math.min(Number(nums[1]), 100);
  return (lo + hi) / 2 / 100;
}

function asFraction(pct) {
  return typeof pct === "number" && Number.isFinite(pct) ? pct / 100 : undefined;
}

function firstFinite(...vals) {
  return vals.find((v) => typeof v === "number" && Number.isFinite(v));
}

function runBtnStyle(disabled) {
  return {
    padding: "8px 16px", borderRadius: 6, border: `1px solid ${C.slate300}`,
    background: disabled ? C.slate100 : C.white, color: C.slate600,
    fontSize: 12, fontWeight: 600, cursor: disabled ? "default" : "pointer",
  };
}

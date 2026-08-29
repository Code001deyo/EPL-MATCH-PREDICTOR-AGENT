import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from "recharts";
import { C, space, type } from "../../theme";
import { axis, grid, tooltipStyle, legendStyle, pct, series } from "../charts/chartTheme";
import { OUTCOME_SPLIT } from "./explainerData";

/* What the model calls, against what actually happened, over one full season.
 *
 * The empty draw column is the entire point of the chart, and an empty column is
 * exactly the thing a bar chart renders as *nothing* — indistinguishable from a
 * category that was never in the data. So the zero is labelled explicitly, in the
 * semantic red, with the count of matches it cost underneath. A reader must be
 * able to tell "predicted 0% of the time" apart from "not measured".
 */
export default function OutcomeSplit() {
  return (
    <div>
      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <BarChart data={OUTCOME_SPLIT} margin={{ top: 16, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid {...grid} />
            <XAxis dataKey="outcome" {...axis} />
            <YAxis {...axis} domain={[0, 70]} tickFormatter={pct} />
            <Tooltip {...tooltipStyle} formatter={(v) => `${v.toFixed(1)}%`} />
            <Legend {...{ wrapperStyle: legendStyle }} />
            <Bar dataKey="predicted" name="Model predicted" fill={series.primary} radius={[4, 4, 0, 0]} />
            <Bar dataKey="actual" name="Actually happened" fill={series.muted} radius={[4, 4, 0, 0]}>
              {OUTCOME_SPLIT.map((row) => (
                <Cell key={row.outcome} fill={series.muted} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* The zero, stated in words. A missing bar cannot say this for itself. */}
      <div style={{
        ...type.body, fontSize: 14, lineHeight: 1.7, color: C.slate600,
        marginTop: space.lg, paddingTop: space.lg,
        borderTop: `1px solid ${C.slate100}`,
      }}>
        <strong style={{ color: C.rose }}>The draw column is empty.</strong>{" "}
        Across all 380 matches the model named a draw zero times. 104 of them
        finished level, so every one was scored wrong before kick-off. This comes
        out of the arithmetic rather than a bug, and the section below explains why
        removing it made the model measurably worse.
      </div>
    </div>
  );
}

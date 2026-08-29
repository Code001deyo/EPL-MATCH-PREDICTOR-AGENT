import { C, radius, space, type } from "../../theme";
import { ACCURACY_LADDER } from "./explainerData";

const MAX = 60;

/* The ladder the whole page rests on: four forecasters, one scale.
 *
 * Horizontal bars rather than vertical, because the labels are sentences ("Always
 * pick the home team") and a vertical axis would either truncate them or turn
 * them sideways. The reader's job here is to compare four lengths against each
 * other, which reads left-to-right without any axis gymnastics.
 *
 * Three roles, three weights, and they are not decoration: the model is the
 * subject, the market is its peer and the only figure that bounds it, and the two
 * baselines are furniture — what you get for free. Painting all four the same
 * would make "the market" and "a random guess" look like equal members of a set.
 */
export default function AccuracyLadder() {
  const colour = {
    subject: C.navy,
    peer: C.blueDark,
    baseline: C.slate400,
  };

  return (
    <div>
      {ACCURACY_LADDER.map((row) => (
        <div key={row.label} style={{ marginBottom: space.md }}>
          <div style={{
            display: "flex", justifyContent: "space-between",
            alignItems: "baseline", gap: space.md, marginBottom: 5,
          }}>
            <span style={{
              ...type.body,
              fontWeight: row.emphasis === "baseline" ? 400 : 600,
              color: row.emphasis === "baseline" ? C.slate500 : C.slate800,
            }}>
              {row.label}
            </span>
            <span style={{
              ...type.bodyStrong,
              color: row.emphasis === "baseline" ? C.slate500 : C.slate800,
              fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap",
            }}>
              {row.value.toFixed(1)}%
            </span>
          </div>

          <div style={{
            background: C.slate100, borderRadius: radius.sm,
            height: 22, width: "100%", overflow: "hidden",
          }}>
            <div
              title={`${row.label} — ${row.value.toFixed(1)}%, ${row.note}`}
              style={{
                width: `${(row.value / MAX) * 100}%`,
                height: "100%",
                background: colour[row.emphasis],
                borderRadius: radius.sm,
              }}
            />
          </div>

          <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: 4 }}>
            {row.note}
          </div>
        </div>
      ))}

      <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, marginTop: space.lg }}>
        Share of 1,140 matches where the predicted outcome was correct. Scale runs to {MAX}%.
      </div>
    </div>
  );
}

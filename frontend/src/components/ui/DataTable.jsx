import { C, radius, type } from "../../theme";

/* One table treatment for the whole app.
 *
 * RecentPredictions, the league table and History each hand-rolled a <table> with
 * different padding, different header casing and different alignment, so three
 * tables on three pages looked like three components. Numerics were left-aligned
 * in all of them, which makes a column of scores genuinely harder to compare.
 *
 * columns: [{ key, header, align, width, minWidth, nowrap, render, numeric }]
 * Any column marked `numeric` is right-aligned and tabular-figured so digits line
 * up vertically. `rowStyle` lets a caller tint qualification or relegation rows
 * without reaching into the markup. */
export default function DataTable({ columns, rows, rowKey, rowStyle, empty, dense = false }) {
  if (!rows || rows.length === 0) {
    return <div style={{ ...type.body, color: C.slate400, padding: "16px 2px" }}>{empty || "Nothing to show."}</div>;
  }
  const pad = dense ? "6px 8px" : "9px 12px";

  return (
    // Wide tables scroll inside their own container; the page body must never
    // scroll horizontally.
    <div style={{ overflowX: "auto", width: "100%" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{
                padding: pad,
                textAlign: c.numeric ? "right" : c.align || "left",
                ...type.micro, color: C.slate400,
                textTransform: "uppercase", letterSpacing: "0.04em",
                borderBottom: `2px solid ${C.slate100}`,
                width: c.width, whiteSpace: "nowrap",
                position: "sticky", top: 0, background: C.white, zIndex: 1,
              }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey ? rowKey(row, i) : i} style={{
              borderBottom: `1px solid ${C.slate100}`,
              ...(rowStyle ? rowStyle(row, i) : null),
            }}>
              {columns.map((c) => (
                <td key={c.key} style={{
                  padding: pad,
                  textAlign: c.numeric ? "right" : c.align || "left",
                  color: C.slate700,
                  // Tabular figures: without this, proportional digits make a
                  // column of numbers ragged and hard to scan.
                  fontVariantNumeric: c.numeric ? "tabular-nums" : "normal",
                  borderRadius: radius.sm,
                  // Without this a label like "Crystal Palace vs Man City" wraps
                  // onto four lines in a narrow column and the row grows to match,
                  // which is why the table scrolls horizontally instead.
                  whiteSpace: c.nowrap ? "nowrap" : "normal",
                  minWidth: c.minWidth,
                }}>
                  {c.render ? c.render(row, i) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

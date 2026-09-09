/* Long rows from the API into the wide shape a chart wants, at a chosen
 * time resolution.
 *
 * The API returns one row per (matchweek, club) because that is what a database
 * stores. Recharts wants one row per x-value with a column per club.
 *
 * **Why resampling is honest here.** A title probability is a step function. It
 * does not drift with the clock — it changes when matches are played and holds
 * still in between, which is why every snapshot is stamped with `as_of`: the
 * moment its matchweek's last match finished. Bucketing those into hours, days,
 * weeks or months is therefore a genuine resampling of a real time series, not
 * an interpolation. The flat stretches between kickoffs are the truth, and the
 * chart draws them as steps rather than sloping between points, because a
 * diagonal line would imply the probability was changing on the Tuesday.
 *
 * Re-running the simulation hourly to make the line wiggle would be worse than
 * useless: the movement would be Monte Carlo sampling noise, and the project
 * already refuses to draw invented movement (see db/race.py).
 */

export const GRANULARITIES = [
  { id: "matchweek", label: "Matchweek" },
  { id: "day", label: "Daily" },
  { id: "week", label: "Weekly" },
  { id: "month", label: "Monthly" },
];

function startOfBucket(date, granularity) {
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return null;

  switch (granularity) {
    case "hour":
      d.setUTCMinutes(0, 0, 0);
      break;
    case "day":
      d.setUTCHours(0, 0, 0, 0);
      break;
    case "week": {
      // ISO weeks: Monday start, which is how a football calendar reads.
      d.setUTCHours(0, 0, 0, 0);
      const weekday = (d.getUTCDay() + 6) % 7;
      d.setUTCDate(d.getUTCDate() - weekday);
      break;
    }
    case "month":
      d.setUTCHours(0, 0, 0, 0);
      d.setUTCDate(1);
      break;
    default:
      return null;
  }
  return d.toISOString();
}

export function bucketLabel(iso, granularity) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const opts =
    granularity === "month"
      ? { month: "short", year: "2-digit", timeZone: "UTC" }
      : granularity === "hour"
      ? { day: "numeric", month: "short", hour: "2-digit", timeZone: "UTC" }
      : { day: "numeric", month: "short", timeZone: "UTC" };
  return d.toLocaleDateString("en-GB", opts);
}

/* points: rows from /race/history. teams: which clubs to include as columns.
 *
 * Returns rows ordered oldest first, each carrying `x` (the axis value) and one
 * numeric column per club, as whole-tenths of a percent.
 */
export function buildSeries(points, teams, granularity = "matchweek") {
  const wanted = new Set(teams);
  const rows = new Map();

  // Sorted so that when two snapshots land in the same bucket the later one
  // wins — a bucket should hold the state at its end, not at its start.
  const ordered = [...points]
    .filter((p) => wanted.has(p.team))
    .sort((a, b) => {
      const byWeek = (a.matchweek || 0) - (b.matchweek || 0);
      return byWeek !== 0 ? byWeek : String(a.as_of || "").localeCompare(String(b.as_of || ""));
    });

  for (const point of ordered) {
    let key;
    let label;
    let sort;

    if (granularity === "matchweek") {
      key = `mw-${point.matchweek}`;
      label = `MW${point.matchweek}`;
      sort = point.matchweek;
    } else {
      const bucket = startOfBucket(point.as_of, granularity);
      // A snapshot with no usable timestamp cannot be placed on a time axis.
      // Dropped rather than given today's date, which would stack the whole
      // season onto one point.
      if (!bucket) continue;
      key = bucket;
      label = bucketLabel(bucket, granularity);
      sort = new Date(bucket).getTime();
    }

    if (!rows.has(key)) rows.set(key, { x: label, __sort: sort, matchweek: point.matchweek });
    const row = rows.get(key);
    row[point.team] = Number(((point.title_prob || 0) * 100).toFixed(1));
    row.matchweek = point.matchweek;
  }

  return [...rows.values()].sort((a, b) => a.__sort - b.__sort);
}

export default buildSeries;

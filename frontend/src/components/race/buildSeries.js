/* Long series -> one row per matchweek, one column per contender, percentages
 * rounded for display. Recharts wants the wide shape; the API returns the long
 * one because that is what a database stores. */
export function buildSeries(points, contenders) {
  const wanted = new Set(contenders);
  const byWeek = new Map();

  for (const point of points) {
    if (!wanted.has(point.team)) continue;
    if (!byWeek.has(point.matchweek)) byWeek.set(point.matchweek, { matchweek: point.matchweek });
    byWeek.get(point.matchweek)[point.team] = Number(((point.title_prob || 0) * 100).toFixed(1));
  }

  return [...byWeek.values()].sort((a, b) => a.matchweek - b.matchweek);
}

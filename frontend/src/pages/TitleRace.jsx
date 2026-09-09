import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import API from "../config";
import Masthead from "../components/Masthead";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import { clubIdentity } from "../components/crest/clubIdentity";
import RaceLeaderboard from "../components/race/RaceLeaderboard";
import { buildSeries, GRANULARITIES } from "../components/race/buildSeries";
import { C } from "../theme";

/* A title race is a set of lines that cross.
 *
 * The first build led with a twenty-row bar chart and put the trend below the
 * fold, which had it backwards: most of those rows sit at 0% and render as empty
 * track, so the loudest thing on the page was a list of clubs with no chance,
 * while the one element that actually shows a race - probability moving over time
 * - was the thing you had to scroll to find.
 *
 * Now the chart leads, every club is plotted, and the list underneath is the
 * chart's key rather than a second visualisation competing with it.
 */
export default function TitleRace() {
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [granularity, setGranularity] = useState("matchweek");
  const [seasons, setSeasons] = useState([]);
  const [season, setSeason] = useState(null);

  // Which seasons have a stored race. Fetched once; the selector defaults to the
  // current one.
  useEffect(() => {
    let live = true;
    axios
      .get(`${API}/race/seasons`)
      .then(({ data }) => {
        if (!live) return;
        setSeasons(data.seasons || []);
        setSeason((held) => held || data.current);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!season) return undefined;
    let live = true;
    setCurrent(null);
    setHistory([]);
    const q = `?season=${encodeURIComponent(season)}`;
    Promise.all([
      axios.get(`${API}/race/current${q}`),
      axios.get(`${API}/race/history${q}`),
    ])
      .then(([now, past]) => {
        if (!live) return;
        setCurrent(now.data);
        setHistory(past.data.points || []);
      })
      .catch(() => live && setError("Could not load the title race."));
    return () => {
      live = false;
    };
  }, [season]);

  const teams = current?.teams || [];

  // Every club in the division, not a shortlist. A club at 0.0% is a fact worth
  // being able to read, and its flat line along the bottom is the shape of a
  // season going wrong.
  const lines = useMemo(() => teams.map((t) => t.team), [teams]);
  const chart = useMemo(
    () => buildSeries(history, lines, granularity),
    [history, lines, granularity]
  );

  // Where the reconstructed weeks end and the live record begins.
  const lastBackfilledX = useMemo(() => {
    const weeks = history.filter((p) => p.kind === "backfill").map((p) => p.matchweek);
    if (!weeks.length) return null;
    const lastWeek = Math.max(...weeks);
    const row = [...chart].reverse().find((r) => r.matchweek <= lastWeek);
    return row ? row.x : null;
  }, [history, chart]);

  // A fixed 0-100 axis wastes most of the plot when the leader is on 50% and
  // sixteen clubs are under 1%. Scale to the data, with headroom.
  const ceiling = useMemo(() => {
    const peak = Math.max(
      0,
      ...chart.flatMap((row) =>
        lines.map((team) => (typeof row[team] === "number" ? row[team] : 0))
      )
    );
    return Math.min(100, Math.max(10, Math.ceil((peak + 8) / 10) * 10));
  }, [chart, lines]);

  const hasTrend = chart.length > 1;

  return (
    <>
      <Masthead title="The title race">
        Every remaining fixture, played out ten thousand times after each refresh.
        A club's line is the share of those simulated seasons it finished top -
        not a forecast, and not a market price.
      </Masthead>

      {error && <EmptyState kind="error" title="Unavailable" detail={error} />}

      {current?.status === "not-simulated" && (
        <EmptyState
          title="Not simulated yet"
          detail="No season simulation has been stored for this campaign. The race is computed after each data refresh."
        />
      )}

      {teams.length > 0 && (
        <>
          <Card style={{ marginBottom: 24 }}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 12,
                alignItems: "flex-start",
                justifyContent: "space-between",
                marginBottom: 16,
              }}
            >
              <div>
                <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: C.slate800 }}>
                  Title probability over time
                </h2>
                <p style={{ margin: "4px 0 0", fontSize: 12, color: C.slate500 }}>
                  All {teams.length} clubs · {season}
                  {current.matchweek ? ` · through matchweek ${current.matchweek}` : ""}
                </p>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <label className="pl-sr-only" htmlFor="race-season">Season</label>
              <select
                id="race-season"
                className="pl-select"
                value={season || ""}
                onChange={(e) => setSeason(e.target.value)}
              >
                {seasons.map((s) => (
                  <option key={s.season} value={s.season}>
                    {s.season}{s.is_current ? " (current)" : ""}
                  </option>
                ))}
              </select>

              <div
                className="pl-seg"
                role="group"
                aria-label="Time resolution"
              >
                {GRANULARITIES.map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    aria-pressed={granularity === g.id}
                    onClick={() => setGranularity(g.id)}
                  >
                    {g.label}
                  </button>
                ))}
              </div>
              </div>
            </div>

            {hasTrend ? (
              /* Deliberately NOT inside .pl-scroll-x. A ResponsiveContainer
                 measures its parent; give it a minWidth inside an overflow-x:auto
                 parent and the two feed each other - the container widens, the
                 parent gains a scrollbar, the observer fires again - which locked
                 the page hard enough that the renderer stopped answering. A line
                 chart reflows on its own and needs no scroll container. */
              <div>
                <ResponsiveContainer width="100%" height={440}>
                  <LineChart data={chart} margin={{ top: 8, right: 16, left: -18, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.slate200} vertical={false} />
                    <XAxis
                      dataKey="x"
                      tick={{ fontSize: 11, fill: C.slate500 }}
                      stroke={C.slate300}
                      minTickGap={24}
                    />
                    <YAxis
                      tickFormatter={(v) => `${v}%`}
                      domain={[0, ceiling]}
                      tick={{ fontSize: 11, fill: C.slate500 }}
                      stroke={C.slate300}
                    />
                    <Tooltip
                      // Sorted and trimmed: twenty entries, most of them 0.0%, is
                      // not a tooltip anybody can read.
                      itemSorter={(item) => -(item.value || 0)}
                      formatter={(value, name) => [`${value}%`, name]}
                      labelFormatter={(v) => v}
                      contentStyle={{
                        fontSize: 12,
                        borderRadius: 8,
                        border: `1px solid ${C.slate200}`,
                        maxHeight: 260,
                        overflow: "hidden",
                      }}
                    />

                    {/* The reconstructed span, marked rather than blended in. */}
                    {lastBackfilledX != null && (
                      <ReferenceArea
                        x1={chart[0].x}
                        x2={lastBackfilledX}
                        fill={C.slate400}
                        fillOpacity={0.09}
                        label={{
                          value: "reconstructed",
                          fontSize: 10,
                          fill: C.slate500,
                          position: "insideTopLeft",
                        }}
                      />
                    )}

                    {lines.map((team) => {
                      // Contenders are drawn heavier. With twenty lines the
                      // alternative is a thicket in which the three clubs that
                      // matter are no more visible than the seventeen that do not.
                      const prob =
                        teams.find((t) => t.team === team)?.title_prob || 0;
                      const major = prob >= 0.005;
                      return (
                        <Line
                          key={team}
                          type={granularity === "matchweek" ? "monotone" : "stepAfter"}
                          dataKey={team}
                          stroke={clubIdentity(team).primary}
                          strokeWidth={major ? 2.5 : 1.25}
                          strokeOpacity={major ? 1 : 0.45}
                          dot={major ? { r: 2.5, strokeWidth: 0 } : false}
                          activeDot={{ r: 5 }}
                          connectNulls
                          // No entry animation. Three reasons, in order of
                          // weight: a reader who set prefers-reduced-motion
                          // cannot be honoured by CSS here, because this is a
                          // JS-driven SVG animation the stylesheet cannot reach;
                          // twenty lines drawing themselves in is noise, not
                          // information; and it made every QA screenshot capture
                          // an empty plot area, which is a check that silently
                          // stops checking.
                          isAnimationActive={false}
                        />
                      );
                    })}
                  </LineChart>
                </ResponsiveContainer>

                {granularity !== "matchweek" && (
                  <p className="pl-caveat">
                    Drawn as steps, not slopes. A title probability does not drift
                    with the clock - it moves when matches are played and holds
                    still in between, so each point sits at the moment its
                    matchweek's last match finished. A sloping line would claim the
                    odds were changing on the Tuesday, and re-simulating hourly to
                    make the line wander would only be drawing sampling noise.
                  </p>
                )}
              </div>
            ) : (
              /* One stored snapshot is a point, not a trend. */
              <EmptyState
                title="Only one matchweek stored so far"
                detail="The trend appears once a second simulation has been stored - one is written per data refresh."
              />
            )}

            <RaceLeaderboard teams={teams} />

            {hasTrend && (
              <p className="pl-caveat">
                The shaded span is reconstruction, not record. Those points were
                computed by today's model working back from the table as it stood
                at the time - and today's model has been trained on the matches it
                is being asked to simulate. They answer "what would we say now
                about week 3", which is a different question from "what did we say
                in week 3". Everything after the shading is what the model actually
                said, when it said it.
              </p>
            )}
          </Card>

          <Card>
            <h2 style={{ margin: "0 0 4px", fontSize: 14, fontWeight: 700, color: C.slate800 }}>
              What this is, and is not
            </h2>
            <p className="pl-caveat" style={{ borderColor: C.blue }}>
              Every remaining fixture is scored by the same model the rest of the
              site uses, then played out as independent draws from its goal rates.
              Real seasons are not independent: injuries persist, a club with
              nothing to play for in May is not the club that played in March, and
              managers change. Rates are also held fixed - the model does not learn
              anything inside a simulated season. So these are the probabilities
              implied by today's model under independence, which is a narrower
              claim than "the probability this club wins the league".
            </p>
            <p className="pl-caveat">
              Premier League only. The Championship is not simulated here: the
              stored fixture list covers the Premier League alone, and a season
              cannot be played out without knowing which matches remain.
            </p>
          </Card>
        </>
      )}
    </>
  );
}

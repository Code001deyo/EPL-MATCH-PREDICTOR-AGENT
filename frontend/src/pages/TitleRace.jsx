import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
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
import { buildSeries } from "../components/race/buildSeries";
import { C } from "../theme";

/* Who wins the league, and how that answer has moved.
 *
 * The number on this page is a frequency, not an opinion: the remaining fixtures
 * are simulated ten thousand times and the finishes are counted. That is worth
 * saying on the page itself, which is what the caveat at the bottom does — a bar
 * chart of percentages otherwise reads like a market, and this is not one.
 */
export default function TitleRace() {
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      axios.get(`${API}/race/current`),
      axios.get(`${API}/race/history`),
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
  }, []);

  const teams = current?.teams || [];

  // The chart follows whoever is currently in contention rather than a fixed
  // list — a hardcoded "big six" would leave out the season's actual story.
  const contenders = useMemo(
    () => teams.filter((t) => (t.title_prob || 0) > 0.005).slice(0, 6).map((t) => t.team),
    [teams]
  );

  const chart = useMemo(() => buildSeries(history, contenders), [history, contenders]);

  // Where the reconstructed weeks end and the live record begins. Shaded on the
  // chart, because the two are not the same kind of number.
  const lastBackfilled = useMemo(() => {
    const reconstructed = history.filter((p) => p.kind === "backfill");
    return reconstructed.length
      ? Math.max(...reconstructed.map((p) => p.matchweek))
      : null;
  }, [history]);

  return (
    <>
      <Masthead title="The title race">
        Every remaining fixture, played out ten thousand times. A club's number is
        the share of those simulated seasons it finished top — not a forecast, and
        not a market price.
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
            <SectionHead
              title="Title probability"
              detail={`After matchweek ${current.matchweek} · change since the previous week`}
            />
            <RaceLeaderboard teams={teams} />
          </Card>

          {chart.length > 1 && (
            <Card style={{ marginBottom: 24 }}>
              <SectionHead
                title="How it has moved"
                detail="Title probability by matchweek"
              />
              <div className="pl-scroll-x">
                <ResponsiveContainer width="100%" height={320} minWidth={280}>
                  <AreaChart data={chart} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.slate200} vertical={false} />
                    <XAxis
                      dataKey="matchweek"
                      tickFormatter={(v) => `MW${v}`}
                      tick={{ fontSize: 11, fill: C.slate500 }}
                      stroke={C.slate300}
                    />
                    <YAxis
                      tickFormatter={(v) => `${v}%`}
                      domain={[0, 100]}
                      tick={{ fontSize: 11, fill: C.slate500 }}
                      stroke={C.slate300}
                    />
                    <Tooltip
                      formatter={(value, name) => [`${value}%`, name]}
                      labelFormatter={(v) => `Matchweek ${v}`}
                      contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${C.slate200}` }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />

                    {/* The reconstructed region, marked rather than blended in. */}
                    {lastBackfilled != null && (
                      <ReferenceArea
                        x1={chart[0].matchweek}
                        x2={lastBackfilled}
                        fill={C.slate400}
                        fillOpacity={0.08}
                        label={{ value: "reconstructed", fontSize: 10, fill: C.slate500, position: "insideTopLeft" }}
                      />
                    )}

                    {contenders.map((team) => (
                      <Area
                        key={team}
                        type="monotone"
                        dataKey={team}
                        stroke={clubIdentity(team).primary}
                        fill={clubIdentity(team).primary}
                        fillOpacity={0.08}
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                      />
                    ))}
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <p className="pl-caveat">
                The shaded weeks are reconstructions, not a record. They were
                computed by today's model working back from the table as it stood
                at the time — and today's model has been trained on the matches it
                is being asked to simulate. They answer "what would we say now
                about week 3", which is a different question from "what did we say
                in week 3". Everything after the shading is what the model
                actually said, when it said it.
              </p>
            </Card>
          )}

          <Card>
            <SectionHead title="What this is, and is not" />
            <p className="pl-caveat" style={{ borderColor: C.blue }}>
              Every remaining fixture is scored by the same model the rest of the
              site uses, then played out as independent draws from its goal rates.
              Real seasons are not independent: injuries persist, a club with
              nothing to play for in May is not the club that played in March, and
              managers change. Rates are also held fixed — the model does not learn
              anything inside a simulated season. So these are the probabilities
              implied by today's model under independence, which is a narrower
              claim than "the probability this club wins the league".
            </p>
          </Card>
        </>
      )}
    </>
  );
}

function SectionHead({ title, detail }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: C.slate800 }}>{title}</h2>
      {detail && (
        <p style={{ margin: "4px 0 0", fontSize: 12, color: C.slate500 }}>{detail}</p>
      )}
    </div>
  );
}

import { useState, useEffect } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import EmptyState from "../ui/EmptyState";
import { C, space, type, radius } from "../../theme";
import { API } from "../../config";

const SHOW = 8;

/* The dashboard had no upcoming-fixtures panel at all.
 *
 * /fixtures/upcoming has been serving live data the whole time (371 fixtures
 * for the current season) but nothing on the dashboard consumed it, and
 * /fixtures/current was called from nowhere in the app. "Upcoming fixtures
 * don't show" was therefore true of the UI, not of the API.
 *
 * These come straight from the Premier League feed, not the local database:
 * ingestion only ever stores *played* matches, so an unplayed fixture does not
 * exist in the DB and never could be listed from it. */
export default function UpcomingFixtures() {
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/fixtures/upcoming`)
      .then(r => {
        if (cancelled) return;
        // The endpoint reports upstream trouble in-band with HTTP 200, so a
        // body carrying `error` is a failure even though the request succeeded.
        if (r.data?.error) { setState("error"); return; }
        setData(r.data);
        setState("ready");
      })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, []);

  const fixtures = (data?.fixtures || []).slice(0, SHOW);

  return (
    <Card>
      <SectionTitle sub={
        data?.season
          ? `${data.season} · ${data.upcoming_count} still to play · live from the Premier League feed`
          : "Live from the Premier League feed"
      }>
        Upcoming fixtures
      </SectionTitle>

      {state === "loading" && <EmptyState kind="loading" title="Loading fixtures…" />}

      {state === "error" && (
        <EmptyState
          kind="error"
          title="Could not reach the fixture feed"
          detail="The Premier League API did not answer. Nothing is shown rather than a stale list."
        />
      )}

      {state === "ready" && fixtures.length === 0 && (
        <EmptyState
          kind="not-measured"
          title="No fixtures scheduled"
          detail="The season has either finished or the next round is not yet published."
        />
      )}

      {state === "ready" && fixtures.length > 0 && (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: space.xs }}>
            {fixtures.map(f => (
              <div key={f.pl_fixture_id} style={{
                display: "grid",
                // Matchweek column is fixed; the teams take the slack and the
                // kickoff wraps under on narrow screens rather than overflowing.
                gridTemplateColumns: "minmax(44px, auto) minmax(0, 1fr) minmax(0, auto)",
                gap: space.md, alignItems: "center",
                padding: `${space.sm}px ${space.md}px`,
                borderRadius: radius.sm,
                background: C.slate50,
              }}>
                <span style={{ ...type.micro, color: C.slate500 }}>MW{f.matchweek}</span>
                <span style={{ ...type.bodyStrong, color: C.slate800 }}>
                  {f.home_team} <span style={{ color: C.slate400, fontWeight: 400 }}>v</span> {f.away_team}
                </span>
                <span style={{ ...type.micro, fontWeight: 400, color: C.slate400, textAlign: "right" }}>
                  {f.kickoff}
                </span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: space.md, ...type.label }}>
            <Link to="/predict" style={{ color: C.blueDark, textDecoration: "none" }}>
              Predict a fixture →
            </Link>
          </div>
        </>
      )}
    </Card>
  );
}

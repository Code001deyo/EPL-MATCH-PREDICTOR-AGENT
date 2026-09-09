import Crest from "../crest/Crest";
import { clubIdentity } from "../crest/clubIdentity";
import { C } from "../../theme";

/* The standings, in the shape a football table is actually read.
 *
 * Position, badge, club, then numbers right-aligned and tabular so the digits
 * line up down the column. That last detail is what makes a table scannable and
 * it is the one most web tables get wrong.
 *
 * This replaced a list of twenty progress bars. Most of them sat at 0% and
 * rendered as empty track, so the loudest thing on the page was the clubs with
 * no chance. A real table carries more information in less space.
 *
 * The colour chip beside each badge is that club's line on the chart above, so a
 * row can be tied to a line without a lookup. The badge says which club; the chip
 * says which line. Neither does both.
 */
export default function RaceLeaderboard({ teams, showChange = true }) {
  if (!teams.length) return null;

  return (
    <div className="pl-scroll-x" style={{ marginTop: 20 }}>
      <table className="pl-table">
        <thead>
          <tr>
            <th className="pl-num" scope="col">Pos</th>
            <th scope="col">Club</th>
            <th className="pl-num" scope="col">Pl</th>
            <th className="pl-num" scope="col">Pts</th>
            <th className="pl-num" scope="col">GD</th>
            <th className="pl-num" scope="col">Title</th>
            <th className="pl-num" scope="col">Top 4</th>
            <th className="pl-num" scope="col">Rel</th>
            {showChange && <th className="pl-num" scope="col">Chg</th>}
          </tr>
        </thead>
        <tbody>
          {teams.map((team, i) => (
            <Row key={team.team} team={team} rank={i + 1} showChange={showChange} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ team, rank, showChange }) {
  const club = clubIdentity(team.team);
  const delta = team.title_delta;

  return (
    <tr>
      <td className="pl-num pl-pos" data-label="Pos">{rank}</td>

      <td data-label="Club">
        <span className="pl-club">
          <i className="pl-club-chip" style={{ background: club.primary }} aria-hidden="true" />
          <Crest team={team.team} size={22} />
          <span className="pl-club-name">{club.name || team.team}</span>
        </span>
      </td>

      <td className="pl-num" data-label="Played">{team.played}</td>
      <td className="pl-num pl-strong" data-label="Points">{team.points}</td>
      <td className="pl-num" data-label="Goal difference">
        {team.goal_difference > 0 ? `+${team.goal_difference}` : team.goal_difference}
      </td>

      <td className="pl-num pl-strong" data-label="Title">{pct(team.title_prob)}</td>
      <td className="pl-num" data-label="Top 4">{pct(team.top_four_prob)}</td>
      <td className="pl-num" data-label="Relegation">{pct(team.relegation_prob)}</td>

      {showChange && (
        <td className="pl-num" data-label="Change" style={{ color: deltaColour(delta) }}>
          {delta == null ? "" : formatDelta(delta)}
        </td>
      )}
    </tr>
  );
}

/* Whole tenths. The simulation does not distinguish 52.31% from 52.36% in a way
 * anyone should act on, and a second decimal would imply it does. */
function pct(value) {
  if (value == null) return "-";
  const p = value * 100;
  if (p >= 99.95) return "100%";
  if (p < 0.05) return "0%";
  return `${p.toFixed(1)}%`;
}

function formatDelta(delta) {
  const points = delta * 100;
  if (Math.abs(points) < 0.05) return "-";
  return `${points > 0 ? "▲" : "▼"}${Math.abs(points).toFixed(1)}`;
}

function deltaColour(delta) {
  if (delta == null || Math.abs(delta * 100) < 0.05) return C.slate400;
  return delta > 0 ? "#2f8f5b" : "#b3123a";
}

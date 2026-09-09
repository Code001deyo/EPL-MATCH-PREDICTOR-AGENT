import { clubIdentity } from "../crest/clubIdentity";
import { C } from "../../theme";

/* The chart's key: every club, its line colour, and its current probability.
 *
 * This started as twenty rows each carrying a progress bar and a monogram badge.
 * Both had to go. Fifteen of the bars sat at 0% and rendered as empty track, so
 * the bulk of the page was clubs with no chance; and the badge was a 26px
 * monogram that read as a favicon rather than a crest, decorating a row that
 * already said the club's name.
 *
 * What replaces them does the job the bar was failing at — tying a name to a line
 * on the chart above — using the one thing that can: the line's own colour. All
 * twenty clubs are listed, because every one of them is in the simulation and a
 * club at 0.0% is a fact worth being able to read.
 */
export default function RaceLeaderboard({ teams }) {
  if (!teams.length) return null;

  return (
    <div style={{ marginTop: 20 }}>
      <div className="pl-race-key" role="list">
        {teams.map((team, i) => (
          <KeyRow key={team.team} team={team} rank={i + 1} />
        ))}
      </div>
    </div>
  );
}

function KeyRow({ team, rank }) {
  const club = clubIdentity(team.team);
  const percent = (team.title_prob || 0) * 100;
  const delta = team.title_delta;

  return (
    <div className="pl-race-key-row" role="listitem">
      <span className="pl-race-rank">{rank}</span>

      {/* Same colour and stroke weight as this club's line on the chart, so the
          eye can move between key and plot without a lookup. */}
      <span
        aria-hidden="true"
        className="pl-race-swatch"
        style={{ background: club.primary }}
      />

      <span className="pl-race-club">{club.name || team.team}</span>

      <span className="pl-race-pct">
        {percent >= 0.05 ? `${percent.toFixed(1)}%` : "0%"}
      </span>

      <span className="pl-race-move" style={{ color: deltaColour(delta) }}>
        {delta == null ? "" : formatDelta(delta)}
      </span>

      {/* Colour and an arrow are the only visual carriers here, and several clubs
          share a palette — so each row states itself in words for a screen reader. */}
      <span className="pl-sr-only">{describe(team, percent, delta)}</span>
    </div>
  );
}

function describe(team, percent, delta) {
  const base = `${team.team}: ${percent.toFixed(1)}% chance of winning the title, ${team.points} points from ${team.played} played`;
  if (delta == null) return base;
  const change = (delta * 100).toFixed(1);
  return `${base}, ${delta >= 0 ? "up" : "down"} ${Math.abs(change)} percentage points since the previous matchweek`;
}

function formatDelta(delta) {
  const points = delta * 100;
  if (Math.abs(points) < 0.05) return "";
  return `${points > 0 ? "▲" : "▼"}${Math.abs(points).toFixed(1)}`;
}

function deltaColour(delta) {
  if (delta == null || Math.abs(delta * 100) < 0.05) return C.slate400;
  return delta > 0 ? "#2f8f5b" : "#b3123a";
}

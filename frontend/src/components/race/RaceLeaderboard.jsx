import Crest from "../crest/Crest";
import { clubIdentity } from "../crest/clubIdentity";
import { C } from "../../theme";

/* One club's row in the title race.
 *
 * Split out of pages/TitleRace.jsx when that file passed the ~200-line mark. The
 * seam is real rather than arbitrary: this is presentation of a single club,
 * the page is composition and data loading.
 */
export default function RaceLeaderboard({ teams }) {
  return (
    <div role="list">
      {teams.map((team, i) => (
        <RaceRow key={team.team} team={team} rank={i + 1} />
      ))}
    </div>
  );
}

function RaceRow({ team, rank }) {
  const club = clubIdentity(team.team);
  const percent = (team.title_prob || 0) * 100;
  const delta = team.title_delta;

  return (
    <div className="pl-race-row" role="listitem">
      <div className="pl-race-rank">{rank}</div>

      <div className="pl-race-name">
        <Crest team={team.team} size={26} />
        <span>{club.name || team.team}</span>
      </div>

      <div className="pl-race-track-cell">
        <div className="pl-race-track">
          <div
            className="pl-race-fill"
            style={{
              // A floor of 2px so a club on 0.1% is visibly present rather than
              // rendering as nothing, which would read as eliminated.
              width: `${Math.max(percent, percent > 0 ? 1 : 0)}%`,
              minWidth: percent > 0 ? 2 : 0,
              background: club.primary,
            }}
          />
        </div>
      </div>

      <div className="pl-race-prob">
        {percent >= 0.05 ? `${percent.toFixed(1)}%` : "—"}
      </div>

      <div
        className="pl-race-delta"
        style={{ color: deltaColour(delta) }}
        // The bar and the arrow are both colour-coded, so the row needs a text
        // equivalent — several clubs share a palette and colour alone says
        // nothing to a screen reader.
        aria-label={describe(team, percent, delta)}
      >
        {delta == null ? "" : formatDelta(delta)}
      </div>

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
  if (Math.abs(points) < 0.05) return "—";
  return `${points > 0 ? "▲" : "▼"} ${Math.abs(points).toFixed(1)}`;
}

function deltaColour(delta) {
  if (delta == null || Math.abs(delta * 100) < 0.05) return C.slate400;
  return delta > 0 ? "#2f8f5b" : "#b3123a";
}

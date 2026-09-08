import { clubIdentity } from "./clubIdentity";

/* A club badge, drawn rather than fetched.
 *
 * Real Premier League crests are trademarked and there is no licensed set to
 * ship, so this draws a shield in the club's own colours with its three-letter
 * abbreviation — the same identification a scoreboard gives, without borrowing
 * artwork. It renders offline, costs no request, and scales cleanly because it
 * is an SVG rather than a bitmap.
 *
 * If `crestUrl` is set for a club in clubIdentity.js, that image is used instead.
 * That is the path for licensed assets later, per club, without touching this.
 */
export default function Crest({ team, size = 32, title }) {
  const club = clubIdentity(team);
  const label = title || club.name || "Unknown club";

  if (club.crestUrl) {
    return (
      <img
        src={club.crestUrl}
        alt={label}
        width={size}
        height={size}
        style={{ display: "block", objectFit: "contain", flexShrink: 0 }}
      />
    );
  }

  // Font size tracks the badge so a 24px crest and a 48px crest look like the
  // same mark at two sizes, rather than two different marks.
  const fontSize = Math.round(size * 0.34);

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label={label}
      style={{ display: "block", flexShrink: 0 }}
    >
      <title>{label}</title>
      {/* Shield outline: a rounded top and a point at the base. Recognisably a
          football badge without imitating any club's actual crest. */}
      <path
        d="M20 1.5 L36.5 6 V20.5 C36.5 29.5 29.5 35.5 20 38.5 C10.5 35.5 3.5 29.5 3.5 20.5 V6 Z"
        fill={club.primary}
        stroke={club.secondary}
        strokeWidth="2"
      />
      {/* A single band in the secondary colour. Enough to separate two clubs
          whose primaries are close — Arsenal and Liverpool are both red, and
          colour alone would not distinguish them at 24px. */}
      <path
        d="M3.5 13.5 H36.5 V17 H3.5 Z"
        fill={club.secondary}
        opacity="0.85"
      />
      <text
        x="20"
        y="27.5"
        textAnchor="middle"
        fontSize={fontSize}
        fontWeight="800"
        fontFamily="'Inter', system-ui, sans-serif"
        fill={club.text}
        letterSpacing="0.5"
      >
        {club.abbr}
      </text>
    </svg>
  );
}

/* Crest plus name, the pairing almost every row needs.
 *
 * `abbreviate` swaps the full name for the three-letter code below the narrow
 * breakpoint — "Nott'm Forest" and "Crystal Palace" are what break a fixture row
 * on a 320px screen, and truncating them with an ellipsis reads worse than the
 * abbreviation a broadcast would use. */
export function ClubLabel({ team, size = 24, abbreviate = false, style }) {
  const club = clubIdentity(team);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, minWidth: 0, ...style }}>
      <Crest team={team} size={size} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {abbreviate ? club.abbr : club.name || team}
      </span>
    </span>
  );
}

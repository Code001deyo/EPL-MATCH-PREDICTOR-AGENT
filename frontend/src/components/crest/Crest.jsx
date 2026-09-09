import { useState } from "react";
import useClubs from "../../hooks/useClubs";
import { clubIdentity } from "./clubIdentity";

/* A club badge.
 *
 * The official crest, served from the Premier League's own CDN, resolved through
 * the Opta id the backend syncs from PulseLive (see `db/clubs.py`). Nothing is
 * copied into this repository; the page points at the source.
 *
 * These crests are trademarks. That is a fact about them and stays true whatever
 * the project is for; it is recorded here rather than quietly ignored, because
 * the person who ships this commercially later needs to find it.
 *
 * The drawn monogram remains as the fallback, and it earns its place: a club that
 * is not in the clubs table, a new promotion the sync has not seen, or a CDN that
 * is down all end up there instead of at a broken-image icon. The fallback still
 * says which club it is.
 */
export default function Crest({ team, size = 24, title }) {
  const clubs = useClubs();
  const [failed, setFailed] = useState(false);

  const identity = clubIdentity(team);
  const label = title || identity.name || team || "Unknown club";
  const badge = clubs[identity.name]?.badge_url || clubs[team]?.badge_url;

  if (badge && !failed) {
    return (
      <img
        src={badge}
        alt={label}
        width={size}
        height={size}
        loading="lazy"
        // A CDN that stops answering must not leave a broken-image glyph in
        // every row; fall through to the monogram instead.
        onError={() => setFailed(true)}
        style={{ display: "block", objectFit: "contain", flexShrink: 0 }}
      />
    );
  }

  return <Monogram identity={identity} size={size} label={label} />;
}

/* The drawn fallback: a shield in the club's real colours with its abbreviation.
 * Colours are facts about a club rather than protected artwork. */
function Monogram({ identity, size, label }) {
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
      <path
        d="M20 1.5 L36.5 6 V20.5 C36.5 29.5 29.5 35.5 20 38.5 C10.5 35.5 3.5 29.5 3.5 20.5 V6 Z"
        fill={identity.primary}
        stroke={identity.secondary}
        strokeWidth="2"
      />
      <path d="M3.5 13.5 H36.5 V17 H3.5 Z" fill={identity.secondary} opacity="0.85" />
      <text
        x="20"
        y="27.5"
        textAnchor="middle"
        fontSize={fontSize}
        fontWeight="800"
        fontFamily="'Inter', system-ui, sans-serif"
        fill={identity.text}
        letterSpacing="0.5"
      >
        {identity.abbr}
      </text>
    </svg>
  );
}

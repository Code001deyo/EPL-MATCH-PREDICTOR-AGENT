/* Club identity: colours, abbreviation, and an optional real crest.
 *
 * Premier League club crests are registered trademarks. There is no
 * open-licensed set of them, and the ones served from public football APIs are
 * not licensed for reuse either — they are simply reachable. So none are shipped
 * here. What is shipped is each club's actual primary and secondary colour,
 * which are facts about the club rather than protected artwork, and a monogram
 * badge drawn from them (see Crest.jsx).
 *
 * `crestUrl` is the escape hatch. Set it for a club and the badge renders that
 * image instead — so licensed assets can be dropped in later, per club, without
 * touching a component.
 *
 * Names are PulseLive `shortName` values, because that is what the API stores
 * and what `match_results` holds. `alias` covers the other spellings that reach
 * the UI from football-data.co.uk.
 */

export const CLUBS = {
  "Arsenal":        { abbr: "ARS", primary: "#EF0107", secondary: "#FFFFFF", text: "#FFFFFF" },
  "Aston Villa":    { abbr: "AVL", primary: "#670E36", secondary: "#95BFE5", text: "#FFFFFF" },
  "Bournemouth":    { abbr: "BOU", primary: "#DA291C", secondary: "#000000", text: "#FFFFFF" },
  "Brentford":      { abbr: "BRE", primary: "#D20000", secondary: "#FFFFFF", text: "#FFFFFF" },
  "Brighton":       { abbr: "BHA", primary: "#0057B8", secondary: "#FFCD00", text: "#FFFFFF" },
  "Burnley":        { abbr: "BUR", primary: "#6C1D45", secondary: "#99D6EA", text: "#FFFFFF" },
  "Chelsea":        { abbr: "CHE", primary: "#034694", secondary: "#DBA111", text: "#FFFFFF" },
  "Crystal Palace": { abbr: "CRY", primary: "#1B458F", secondary: "#C4122E", text: "#FFFFFF" },
  "Everton":        { abbr: "EVE", primary: "#003399", secondary: "#FFFFFF", text: "#FFFFFF" },
  "Fulham":         { abbr: "FUL", primary: "#000000", secondary: "#CC0000", text: "#FFFFFF" },
  "Hull":           { abbr: "HUL", primary: "#F5A12D", secondary: "#000000", text: "#000000" },
  "Ipswich":        { abbr: "IPS", primary: "#3A64A3", secondary: "#DE2B37", text: "#FFFFFF" },
  "Leeds":          { abbr: "LEE", primary: "#FFCD00", secondary: "#1D428A", text: "#1D428A" },
  "Leicester":      { abbr: "LEI", primary: "#003090", secondary: "#FDBE11", text: "#FFFFFF" },
  "Liverpool":      { abbr: "LIV", primary: "#C8102E", secondary: "#00B2A9", text: "#FFFFFF" },
  "Luton":          { abbr: "LUT", primary: "#F78F1E", secondary: "#002D62", text: "#FFFFFF" },
  "Man City":       { abbr: "MCI", primary: "#6CABDD", secondary: "#1C2C5B", text: "#1C2C5B" },
  "Man Utd":        { abbr: "MUN", primary: "#DA291C", secondary: "#FBE122", text: "#FFFFFF" },
  "Middlesbrough":  { abbr: "MID", primary: "#E21C38", secondary: "#FFFFFF", text: "#FFFFFF" },
  "Newcastle":      { abbr: "NEW", primary: "#241F20", secondary: "#FFFFFF", text: "#FFFFFF" },
  "Norwich":        { abbr: "NOR", primary: "#FFF200", secondary: "#00A650", text: "#00A650" },
  "Nott'm Forest":  { abbr: "NFO", primary: "#DD0000", secondary: "#FFFFFF", text: "#FFFFFF" },
  "Sheffield Utd":  { abbr: "SHU", primary: "#EE2737", secondary: "#000000", text: "#FFFFFF" },
  "Southampton":    { abbr: "SOU", primary: "#D71920", secondary: "#130C0E", text: "#FFFFFF" },
  "Sunderland":     { abbr: "SUN", primary: "#EB172B", secondary: "#211E1E", text: "#FFFFFF" },
  "Tottenham":      { abbr: "TOT", primary: "#132257", secondary: "#FFFFFF", text: "#FFFFFF" },
  "Watford":        { abbr: "WAT", primary: "#FBEE23", secondary: "#ED2127", text: "#11210A" },
  "West Brom":      { abbr: "WBA", primary: "#122F67", secondary: "#FFFFFF", text: "#FFFFFF" },
  "West Ham":       { abbr: "WHU", primary: "#7A263A", secondary: "#1BB1E7", text: "#FFFFFF" },
  "Wolves":         { abbr: "WOL", primary: "#FDB913", secondary: "#231F20", text: "#231F20" },
};

/* Other spellings the same club reaches the UI under. football-data.co.uk and
 * PulseLive disagree on several, and a club rendering as a grey initial because
 * of a spelling is a visible bug. */
const ALIASES = {
  "Manchester City": "Man City",
  "Manchester United": "Man Utd",
  "Man United": "Man Utd",
  "Nottingham Forest": "Nott'm Forest",
  "Nott'ham Forest": "Nott'm Forest",
  "Spurs": "Tottenham",
  "Tottenham Hotspur": "Tottenham",
  "Brighton & Hove Albion": "Brighton",
  "Wolverhampton Wanderers": "Wolves",
  "West Bromwich Albion": "West Brom",
  "Sheffield United": "Sheffield Utd",
  "Leeds United": "Leeds",
  "Newcastle United": "Newcastle",
  "Leicester City": "Leicester",
  "Norwich City": "Norwich",
  "Ipswich Town": "Ipswich",
  "Luton Town": "Luton",
  "Hull City": "Hull",
  "Stoke City": "Stoke",
  "AFC Bournemouth": "Bournemouth",
};

/* A club the manifest does not know still has to render. Neutral Premier League
 * purple with its own initials beats a blank space or a crash — and it looks
 * deliberate enough that a missing entry is not embarrassing, only unbranded. */
const UNKNOWN = { abbr: "", primary: "#37003c", secondary: "#00ff85", text: "#FFFFFF" };

export function clubIdentity(name) {
  if (!name) return { ...UNKNOWN, name: "", abbr: "?" };
  const canonical = CLUBS[name] ? name : (ALIASES[name] || name);
  const club = CLUBS[canonical];
  if (club) return { ...club, name: canonical };

  // Initials from the words of the name: "Real Madrid" -> "RM".
  const abbr = canonical
    .split(/[\s'-]+/)
    .filter(Boolean)
    .map((w) => w[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
  return { ...UNKNOWN, name: canonical, abbr: abbr || "?" };
}

export default clubIdentity;

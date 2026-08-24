import { C, radius } from "../theme";

// Says what a prediction is actually based on. A newly promoted club has no
// Premier League record, so its forecast rests on adjusted Championship form —
// that should be visible on the prediction itself, not buried in the API.
export default function EvidenceNote({ prediction }) {
  if (!prediction) return null;

  const notes = [];
  const { home_team, away_team, evidence } = prediction;

  if (evidence?.home_is_newly_promoted) {
    notes.push(clubNote(home_team, evidence.home_top_flight_matches));
  }
  if (evidence?.away_is_newly_promoted) {
    notes.push(clubNote(away_team, evidence.away_top_flight_matches));
  }

  if (notes.length === 0) return null;

  return (
    <div
      style={{
        marginTop: 14,
        padding: "10px 14px",
        background: "#fff8e6",
        borderLeft: `3px solid ${C.amber}`,
        borderRadius: radius.sm,
        fontSize: 13,
        color: C.slate700,
        lineHeight: 1.6,
      }}
    >
      {notes.map((note, i) => (
        <div key={i}>{note}</div>
      ))}
    </div>
  );
}

function clubNote(club, matches) {
  const played = matches || 0;
  if (played === 0) {
    return `${club} is newly promoted with no Premier League matches this season — this forecast uses their Championship form, adjusted for the step up.`;
  }
  return `${club} is newly promoted — based on ${played} Premier League ${
    played === 1 ? "match" : "matches"
  } plus adjusted Championship form.`;
}

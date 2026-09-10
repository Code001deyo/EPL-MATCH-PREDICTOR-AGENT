// Official Premier League brand colours
// Primary: PL Purple #37003c, Secondary: PL Green #00ff85, Accent: White #ffffff
//
// IMPORTANT: brand colour and semantic colour are separate token sets.
// C.blue (the PL green) is a BRAND accent - used for chart bars, active nav
// state, buttons. `semantic` below is a MEANING accent - used only to say
// "this number is good / marginal / bad". They must never share a hex, or a
// chart bar and a positive delta become visually the same signal.
export const C = {
  // EPL brand
  navy: "#37003c",        // PL primary purple (sidebar/header)
  navyLight: "#4d0052",   // lighter purple for hover/active states
  blue: "#00ff85",        // PL signature green (primary accent) - BRAND, not semantic
  blueDark: "#00b368",    // darker green for hover - distinct from semantic.good
  // The brand green as *text*. #00ff85 measures 1.34:1 on white, which is not
  // readable by anyone; it is a fill colour that had been pressed into service as
  // type. This is the same hue carried down to 4.5:1 so a figure printed in
  // "PL green" can actually be read. Never use C.blue for text on white.
  blueText: "#046c4e",
  // Legacy semantic-ish colours, still used by W/D/L badges elsewhere in the app.
  // W/D/L badge colours. Darkened to clear 4.5:1 as text: the originals were
  // picked as fills and then used as type, where #f59e0b measured 2.14:1 and
  // #00cc6a little better. The badge backgrounds they sit on are unchanged, so
  // the chips still read as the same three colours.
  emerald: "#0c6238",     // win / positive
  amber: "#a4650f",       // draw / warning
  rose: "#c11239",        // loss / negative (PL red)
  // Neutral grays
  slate50: "#f8fafc",
  slate100: "#f1f5f9",
  slate200: "#e2e8f0",
  slate300: "#cbd5e1",
  // Darkened from #94a3b8, which was 2.56:1 on white against WCAG AA's 4.5:1.
  // It is the muted-text colour in 57 places - table headers, captions, units -
  // so it was the single largest source of contrast failures on the site.
  slate400: "#586274",
  // #64748b cleared 4.5:1 on white and measured 4.34 on the pale grey chips it
  // also sits on. A muted colour used on two backgrounds has to satisfy the
  // darker one, so it is set from that constraint rather than from white.
  slate500: "#586274",
  slate600: "#475569",
  slate700: "#334155",
  slate800: "#1e293b",
  white: "#ffffff",

  // Muted text on the purple rail.
  //
  // The sidebar had been using the same slate tokens as the white pages. Those
  // are chosen to be readable on white, so on #37003c they are dark-on-dark -
  // and darkening slate400 to fix the pages made the rail worse. A dark surface
  // needs its own muted colour, going the other way.
  onNavyMuted: "#c9b8d0",
};

// Semantic tokens: judge a number, never decorate a chart with these.
// Deliberately muted relative to the vivid brand green - a model that beats
// its baseline by 1.3 points should not flash the same colour as the sidebar.
export const semantic = {
  good: "#1c6b41",
  goodBg: "#e7f5ee",
  goodBorder: "#bfe3d0",
  warn: "#8f5709",
  warnBg: "#fbf1e2",
  warnBorder: "#efd6a8",
  bad: "#a81034",
  badBg: "#fbe9ee",
  badBorder: "#f0bfcd",
  // Matched to slate500. It held #64748b after that was darkened, which measured
  // 4.34:1 on its own neutralBg tint - and only showed on production, where a
  // delta happened to be neutral and local's never was.
  neutral: "#586274",
  neutralBg: "#f1f5f9",
  neutralBorder: "#e2e8f0",
};

export const shadow = {
  card: "0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)",
  md: "0 4px 16px rgba(0,0,0,0.10)",
  lg: "0 8px 32px rgba(0,0,0,0.12)",
};

export const radius = { sm: 6, md: 10, lg: 14 };

// Spacing scale (px). Use instead of ad hoc gap/margin/padding numbers.
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };

// Type scale: { size, weight, lineHeight }. Encodes the page's hierarchy so
// "the most important thing" and "the least important thing" don't render
// at the same 15px/700 as they did before this pass.
export const type = {
  micro:   { fontSize: 11, fontWeight: 600, lineHeight: 1.3 },
  label:   { fontSize: 12, fontWeight: 600, lineHeight: 1.3 },
  body:    { fontSize: 13, fontWeight: 400, lineHeight: 1.6 },
  bodyStrong: { fontSize: 13, fontWeight: 600, lineHeight: 1.5 },
  section: { fontSize: 14, fontWeight: 700, lineHeight: 1.3 },
  title:   { fontSize: 18, fontWeight: 700, lineHeight: 1.3 },
  page:    { fontSize: 24, fontWeight: 700, lineHeight: 1.25 },
  stat:    { fontSize: 34, fontWeight: 800, lineHeight: 1 },
  statLg:  { fontSize: 44, fontWeight: 800, lineHeight: 1 },
};

export const SIDEBAR_W = 220;

// Breakpoints. The app previously had no media queries at all: a fixed 220px
// sidebar margin and hard `gridTemplateColumns` meant every layout squeezed
// rather than reflowed, and the dashboard was unusable below ~1100px.
export const bp = { sm: 640, md: 900, lg: 1200 };

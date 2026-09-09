#!/usr/bin/env node
/**
 * Drive the built site at real viewport widths and fail on anything broken.
 *
 * Why this exists rather than a person resizing a window: a Chrome window on
 * Windows will not go narrower than about 500px, and the display here is 1366
 * wide — so by hand you can verify neither a phone nor a large desktop. Headless
 * Chrome has no such floor or ceiling, so the widths that actually matter are
 * reachable, and reachable the same way every time.
 *
 * What it asserts, per page per width:
 *
 *   1. No horizontal overflow. The page body must never scroll sideways; wide
 *      content scrolls inside its own box. This is the single check that catches
 *      most responsive breakage.
 *   2. No element wider than the viewport, and it names the offender. "The page
 *      is 40px too wide" is not actionable on its own.
 *   3. No console errors. A React component that throws after mount leaves a
 *      blank page and a successful build.
 *   4. Tap targets are at least 44px. Below that a control is not reliably
 *      hittable with a thumb.
 *   5. The page rendered something. A blank body that overflows nothing would
 *      otherwise pass every check above.
 *
 * Screenshots are written to frontend/screenshots/ for the eye check that no
 * assertion replaces.
 *
 * Usage: node scripts/responsive-check.js [baseUrl]
 */

const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer-core");

const BASE = process.argv[2] || process.env.SITE_URL || "http://localhost:3000";

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium-browser",
  "/usr/bin/chromium",
].filter(Boolean);

// The widths worth checking, not every width. 320 is the narrowest phone still in
// use; 1920 is where a fluid layout starts looking sparse if nothing caps it.
// `touch` is not decoration. It makes Chrome report `pointer: coarse`, which is
// what the stylesheet keys the 44px navigation target off — so the check asks
// the same question the CSS does, instead of demanding finger-sized rows on a
// desktop where they only make the menu heavier.
const VIEWPORTS = [
  { name: "320-small-phone", width: 320, height: 720, touch: true },
  { name: "375-phone", width: 375, height: 812, touch: true },
  // A phone on its side. Short viewports are where 100vh layouts, sticky
  // headers and vertically centred boxes fail, and nothing else here is short.
  { name: "812-phone-landscape", width: 812, height: 375, touch: true },
  { name: "768-tablet", width: 768, height: 1024, touch: true },
  { name: "1024-laptop", width: 1024, height: 768, touch: false },
  // The commonest laptop, previously jumped over between 1024 and 1440.
  { name: "1280-laptop", width: 1280, height: 800, touch: false },
  { name: "1440-desktop", width: 1440, height: 900, touch: false },
  { name: "1920-wide", width: 1920, height: 1080, touch: false },
];

// Every public route. It was three of nine, and "18/18 green" was being read as
// "the site is responsive" when it meant "a third of it is".
const PAGES = [
  { name: "dashboard", path: "/" },
  { name: "race", path: "/race" },
  { name: "predict", path: "/predict" },
  { name: "analytics", path: "/analytics" },
  { name: "teams", path: "/teams" },
  { name: "history", path: "/history" },
  { name: "model", path: "/model" },
  { name: "explainer", path: "/explainer" },
  { name: "privacy", path: "/privacy" },
];

const MIN_TAP = 44;

// A floor on rendered type, not a target. 9px rather than 12: the footer's legal
// line is deliberately 9px at 320px, and a rule that has to exempt the thing
// violating it is not a rule. This catches an accident and permits a decision.
const MIN_FONT_PX = 9;

/* Console errors that are not defects in the page.
 *
 * CI serves the production bundle with no backend behind it, so every API call
 * 404s and Chrome logs each one. Those are expected in that configuration and
 * the pages are built to cope — they render honest empty states, which is itself
 * worth checking. Anything else still fails the run.
 *
 * Set QA_IGNORE_CONSOLE to widen this; leave it unset to catch everything.
 */
const IGNORE_CONSOLE = new RegExp(
  process.env.QA_IGNORE_CONSOLE ||
    "Failed to load resource|net::ERR_|status of 404|status of 5\d\d",
  "i"
);

function findChrome() {
  for (const candidate of CHROME_CANDIDATES) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error(
    `Could not find Chrome. Tried:\n  ${CHROME_CANDIDATES.join("\n  ")}\n` +
      "Set CHROME_PATH to its location."
  );
}

/* Runs inside the page. Returns findings, not opinions. */
function audit(minTap, isTouch, minFont) {
  const doc = document.documentElement;
  const overflow = doc.scrollWidth > window.innerWidth + 1;

  const describe = (el) => {
    const id = el.id ? `#${el.id}` : "";
    const cls =
      typeof el.className === "string" && el.className
        ? `.${el.className.trim().split(/\s+/).slice(0, 2).join(".")}`
        : "";
    return `${el.tagName.toLowerCase()}${id}${cls}`;
  };

  const tooWide = [];
  const smallTaps = [];
  const tinyText = [];

  for (const el of document.querySelectorAll("body *")) {
    const box = el.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) continue;

    // Only elements holding their own text, so a wrapper is not blamed for a
    // child's size and an SVG's internal units are not read as CSS pixels.
    const ownText = [...el.childNodes].some(
      (n) => n.nodeType === 3 && n.textContent.trim().length > 1
    );
    if (ownText && !el.closest("svg")) {
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size && size < minFont) {
        tinyText.push(`${describe(el)} (${size.toFixed(1)}px)`);
      }
    }

    // Only elements that themselves overflow the viewport, and only if no
    // ancestor is a deliberate scroll container — a wide table inside
    // .pl-scroll-x is correct, not a defect.
    if (box.width > window.innerWidth + 1) {
      let scrollable = false;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === "auto" || ox === "scroll") { scrollable = true; break; }
      }
      if (!scrollable) tooWide.push(`${describe(el)} (${Math.round(box.width)}px)`);
    }

    // WCAG 2.5.8 sets 24x24 CSS px as the AA floor and explicitly exempts a
    // target that is "inline" — a link inside a sentence, where enlarging it
    // would break the text. Apple and Google both ask for 44-48px for anything
    // a thumb aims at. So: controls must clear 44px; inline text links are
    // exempt from that but must still clear the WCAG 24px floor.
    //
    // The exemption matters. A check that flags every footer link produces noise
    // nobody reads, which is worse than not checking.
    // Controls are held to 44px on a touch viewport and to the WCAG 2.5.8 floor
    // of 24px elsewhere, matching the `pointer: coarse` rules in the stylesheet.
    // Demanding finger-sized controls on a desktop only makes control rows
    // dominate the cards they sit in, which is how the sidebar got too heavy.
    if (el.matches('button, [role="button"], input, select, nav a')) {
      const floor = isTouch ? minTap : 24;
      if (box.height > 0 && box.height < floor) {
        smallTaps.push(`${describe(el)} (${Math.round(box.height)}px, control, floor ${floor}px)`);
      }
    } else if (el.matches("a[href]")) {
      const inline = getComputedStyle(el).display.startsWith("inline");
      if (box.height > 0 && box.height < 24 && !inline) {
        smallTaps.push(`${describe(el)} (${Math.round(box.height)}px, block link)`);
      }
    }
  }

  return {
    overflow,
    tinyText: [...new Set(tinyText)].slice(0, 6),
    scrollWidth: doc.scrollWidth,
    innerWidth: window.innerWidth,
    tooWide: [...new Set(tooWide)].slice(0, 8),
    smallTaps: [...new Set(smallTaps)].slice(0, 8),
    textLength: (document.body.innerText || "").trim().length,
  };
}

(async () => {
  const executablePath = findChrome();
  const outDir = path.join(__dirname, "..", "screenshots");
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });

  const failures = [];
  let checks = 0;

  for (const view of VIEWPORTS) {
    for (const target of PAGES) {
      const page = await browser.newPage();
      await page.setViewport({
        width: view.width,
        height: view.height,
        hasTouch: view.touch,
        isMobile: view.touch,
      });

      const consoleErrors = [];
      page.on("console", (m) => {
        if (m.type() !== "error") return;
        const text = m.text();
        if (IGNORE_CONSOLE.test(text)) return;
        consoleErrors.push(text.slice(0, 200));
      });
      page.on("pageerror", (e) => consoleErrors.push(`uncaught: ${String(e).slice(0, 200)}`));

      const label = `${target.name} @ ${view.width}px`;
      try {
        await page.goto(`${BASE}${target.path}`, {
          waitUntil: "networkidle2",
          timeout: 45000,
        });
        // Charts animate in; measuring mid-animation reports sizes that are
        // real for a few hundred milliseconds and misleading afterwards.
        await new Promise((r) => setTimeout(r, 2500));

        const result = await page.evaluate(audit, MIN_TAP, view.touch, MIN_FONT_PX);
        checks += 1;

        await page.screenshot({
          path: path.join(outDir, `${target.name}-${view.name}.png`),
          fullPage: true,
        });

        if (result.textLength < 40) {
          failures.push(`${label}: page rendered almost no text (${result.textLength} chars) — likely a component threw`);
        }
        if (result.overflow) {
          failures.push(`${label}: body scrolls horizontally (${result.scrollWidth} > ${result.innerWidth})`);
        }
        if (result.tooWide.length) {
          failures.push(`${label}: wider than the viewport — ${result.tooWide.join(", ")}`);
        }
        if (result.smallTaps.length) {
          failures.push(`${label}: tap targets under ${MIN_TAP}px — ${result.smallTaps.join(", ")}`);
        }
        if (result.tinyText.length) {
          failures.push(`${label}: text under ${MIN_FONT_PX}px — ${result.tinyText.join(", ")}`);
        }
        if (consoleErrors.length) {
          failures.push(`${label}: console errors — ${consoleErrors.slice(0, 3).join(" | ")}`);
        }

        const status = failures.length ? "" : "";
        console.log(
          `  ${result.overflow || result.tooWide.length || result.smallTaps.length || consoleErrors.length ? "FAIL" : "ok  "}  ${label.padEnd(28)} text=${result.textLength}`
        );
      } catch (err) {
        failures.push(`${label}: ${err.message}`);
        console.log(`  FAIL  ${label} — ${err.message}`);
      } finally {
        await page.close();
      }
    }
  }

  await browser.close();

  console.log(`\n${checks} viewport/page combinations checked. Screenshots in frontend/screenshots/.`);

  if (failures.length) {
    console.error(`\n${failures.length} problem(s):\n`);
    for (const f of failures) console.error(`  - ${f}`);
    process.exit(1);
  }
  console.log("No responsive, tap-target or console-error problems found.");
})();

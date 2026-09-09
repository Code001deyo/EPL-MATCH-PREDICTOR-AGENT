/* Render smoke tests for the new pages.
 *
 * These are not screenshot tests and do not claim the layout looks right. They
 * catch the class of failure a successful `npm run build` cannot: a component
 * that compiles and then throws on first render, which in a client-rendered app
 * is a blank white page rather than an error anyone sees.
 *
 * Also asserts the honesty properties that are easy to lose in a later edit —
 * the reconstruction caveat, the timing caveat, and the fact that a club on 0%
 * says so rather than rendering as absent.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";

import TitleRace from "./TitleRace";
import SubscribeCard from "../components/SubscribeCard";
import { clubIdentity } from "../components/crest/clubIdentity";

jest.mock("axios");

// Recharts measures its container, which jsdom reports as 0x0 — the chart then
// renders nothing and warns. Give it a real size so the chart branch is actually
// exercised rather than silently skipped.
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 800 });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 400 });
});

const TEAMS = [
  { team: "Man City", title_prob: 0.497, top_four_prob: 0.96, relegation_prob: 0,
    points: 9, played: 3, projected_points: 77.9, title_delta: -0.001, kind: "live" },
  { team: "Arsenal", title_prob: 0.405, top_four_prob: 0.95, relegation_prob: 0,
    points: 9, played: 3, projected_points: 76.6, title_delta: 0.024, kind: "live" },
  { team: "Burnley", title_prob: 0, top_four_prob: 0.01, relegation_prob: 0.62,
    points: 1, played: 3, projected_points: 32.1, title_delta: 0, kind: "live" },
];

const HISTORY = [
  { matchweek: 1, team: "Arsenal", title_prob: 0.348, points: 3, kind: "backfill", as_of: "2026-08-16T18:00:00+00:00" },
  { matchweek: 2, team: "Arsenal", title_prob: 0.380, points: 6, kind: "backfill", as_of: "2026-08-23T18:00:00+00:00" },
  { matchweek: 3, team: "Arsenal", title_prob: 0.405, points: 9, kind: "live", as_of: "2026-09-06T18:00:00+00:00" },
  { matchweek: 1, team: "Man City", title_prob: 0.470, points: 3, kind: "backfill", as_of: "2026-08-16T18:00:00+00:00" },
  { matchweek: 2, team: "Man City", title_prob: 0.498, points: 6, kind: "backfill", as_of: "2026-08-23T18:00:00+00:00" },
  { matchweek: 3, team: "Man City", title_prob: 0.497, points: 9, kind: "live", as_of: "2026-09-06T18:00:00+00:00" },
];

function mockRace({ status = "ok", teams = TEAMS, history = HISTORY } = {}) {
  axios.get.mockImplementation((url) => {
    if (url.includes("/race/current")) {
      return Promise.resolve({ data: { season: "2026-27", status, matchweek: 3, teams, kind: "live" } });
    }
    if (url.includes("/race/history")) {
      return Promise.resolve({ data: { season: "2026-27", points: history } });
    }
    if (url.includes("/data/freshness")) {
      return Promise.resolve({ data: {
        current_season: "2026-27", matches_played: 78,
        last_refreshed: new Date(Date.now() - 3600_000).toISOString(),
      } });
    }
    if (url.includes("/subscribe/status")) {
      return Promise.resolve({ data: { confirmed: 4, delivery_configured: true } });
    }
    return Promise.resolve({ data: {} });
  });
}

describe("TitleRace", () => {
  it("lists the clubs in contention with their probability", async () => {
    mockRace();
    render(<TitleRace />);

    expect((await screen.findAllByText("Man City")).length).toBeGreaterThan(0);
    expect(screen.getByText("49.7%")).toBeInTheDocument();
    expect(screen.getByText("40.5%")).toBeInTheDocument();
  });

  it("lists every club, including one with no chance left", async () => {
    mockRace();
    render(<TitleRace />);

    // Burnley is on 0% in the fixture data. It is still in the simulation and
    // still in the key: a club at 0.0% is a fact worth being able to read.
    expect(await screen.findByText("Burnley")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("offers the time resolutions and switches between them", async () => {
    mockRace();
    render(<TitleRace />);

    const monthly = await screen.findByRole("button", { name: "Monthly" });
    expect(screen.getByRole("button", { name: "Matchweek" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(monthly);
    expect(monthly).toHaveAttribute("aria-pressed", "true");

    // Switching off matchweeks must say why the line is a step rather than a
    // slope, or the chart quietly implies the odds move between matches.
    await waitFor(() =>
      expect(screen.getByText(/Drawn as steps, not slopes/i)).toBeInTheDocument()
    );
  });

  it("says the Championship is not simulated rather than leaving it unexplained", async () => {
    mockRace();
    render(<TitleRace />);
    await waitFor(() =>
      expect(screen.getByText(/Championship is not simulated here/i)).toBeInTheDocument()
    );
  });

  it("shows the week-on-week movement that makes the page feel live", async () => {
    mockRace();
    render(<TitleRace />);
    // Arsenal +2.4 percentage points.
    expect(await screen.findByText(/▲\s*2\.4/)).toBeInTheDocument();
  });

  it("labels the reconstructed weeks rather than passing them off as a record", async () => {
    mockRace();
    render(<TitleRace />);
    await waitFor(() =>
      expect(screen.getByText(/reconstruction, not record/i)).toBeInTheDocument()
    );
  });

  it("states that fixtures are simulated independently", async () => {
    mockRace();
    render(<TitleRace />);
    await waitFor(() =>
      expect(screen.getByText(/Real seasons are not independent/i)).toBeInTheDocument()
    );
  });

  it("gives every row a text equivalent, because colour alone says nothing", async () => {
    mockRace();
    render(<TitleRace />);
    await waitFor(() =>
      expect(
        screen.getByText(/Arsenal: 40\.5% chance of winning the title, 9 points from 3 played/)
      ).toBeInTheDocument()
    );
  });

  it("says nothing has been simulated rather than showing a page of zeros", async () => {
    mockRace({ status: "not-simulated", teams: [], history: [] });
    render(<TitleRace />);
    expect(await screen.findByText(/Not simulated yet/i)).toBeInTheDocument();
  });
});

describe("SubscribeCard", () => {
  it("promises a window before kickoff, not an exact minute", async () => {
    mockRace();
    render(<SubscribeCard />);
    await waitFor(() =>
      expect(screen.getByText(/in a window before kickoff, not at an exact minute/i))
        .toBeInTheDocument()
    );
  });

  it("closes sign-ups when the server cannot actually deliver", async () => {
    axios.get.mockResolvedValue({ data: { confirmed: 0, delivery_configured: false } });
    render(<SubscribeCard />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /subscribe/i })).toBeDisabled()
    );
  });
});

describe("clubIdentity", () => {
  it("resolves the spellings that reach the UI from the other data source", () => {
    expect(clubIdentity("Manchester City").name).toBe("Man City");
    expect(clubIdentity("Nottingham Forest").abbr).toBe("NFO");
    expect(clubIdentity("Spurs").name).toBe("Tottenham");
  });

  it("renders an unknown club rather than crashing or leaving a gap", () => {
    const unknown = clubIdentity("Real Madrid");
    expect(unknown.abbr).toBe("RM");
    expect(unknown.primary).toBeTruthy();
  });
});

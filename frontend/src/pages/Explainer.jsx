import Card from "../components/ui/Card";
import SectionTitle from "../components/ui/SectionTitle";
import DataTable from "../components/ui/DataTable";
import AccuracyLadder from "../components/explainer/AccuracyLadder";
import OutcomeSplit from "../components/explainer/OutcomeSplit";
import { P, Pull, Aside } from "../components/explainer/prose";
import { ALTERNATIVES, BY_SEASON, MEASURED_ON } from "../components/explainer/explainerData";
import { C, space, type } from "../theme";

/* The public explanation of what this model's accuracy actually means.
 *
 * It exists because the headline number is the most misread thing on the site.
 * "53.6% correct" reads as a poor grade against an assumed 100%, when the figure
 * that bounds it is the bookmakers' 54.2%. A visitor has no way to know that
 * unless the site says so. Every other page reports what the model did; this is
 * the only place that says what a good answer would even look like.
 *
 * Deliberately static: see the note in explainerData.js. The Dashboard and Model
 * pages remain the live view.
 */

// One rhythm for the whole page. Prose needs more air than a dashboard does, and
// the cards here carry paragraphs rather than numbers, so they are padded wider
// than the shared default and spaced further apart.
const CARD = { padding: space.xxl, marginBottom: space.xl };

export default function Explainer() {
  return (
    <div style={{ maxWidth: 800 }}>
      <header style={{ marginBottom: space.xxxl }}>
        <div style={{
          ...type.micro, color: C.slate400, letterSpacing: "0.12em",
          textTransform: "uppercase", marginBottom: space.md,
        }}>
          Understanding the predictions
        </div>
        <h1 style={{ ...type.page, color: C.slate800, margin: 0, marginBottom: space.lg }}>
          How good can a football model be?
        </h1>
        <div style={{ ...type.body, fontSize: 15, lineHeight: 1.7, color: C.slate600, maxWidth: "62ch" }}>
          Most people guess far too high. These figures come from 1,140 Premier
          League matches, and from testing five different approaches against each
          other.
        </div>
      </header>

      <Card style={CARD}>
        <SectionTitle level="primary" sub="Share of the same 1,140 fixtures called correctly">
          Start with the right benchmark
        </SectionTitle>
        <P>
          A prediction model needs something to be compared against. On its own,
          53% sounds poor. Next to the right numbers it looks quite different.
        </P>
        <P>
          We scored four forecasters on the same three seasons. One of them is the
          betting market's closing line, the price bookmakers settle on just before
          kick-off, after they have absorbed team news, injuries, weather and a lot
          of well-informed money. It is about as close to a ceiling as football gets.
        </P>

        <div style={{ margin: `${space.xxl}px 0` }}>
          <AccuracyLadder />
        </div>

        <Pull value="0.6" unit=" pts">
          The gap between this model and the entire betting market. Not twenty
          points. Not ten.
        </Pull>

        <P>
          So the model is not falling short of some obvious higher number. It has
          more or less caught up with the best-informed forecaster in the sport.
          What is left over is not a modelling problem. Football is simply hard to
          predict.
        </P>
      </Card>

      <Card style={CARD}>
        <SectionTitle level="primary">Why 60% is out of reach</SectionTitle>
        <P>
          If the bookmakers manage 54.2% with every advantage available to them,
          then 65% or 70% is not an ambitious target. It means something has gone
          wrong in the measurement.
        </P>
        <P>
          Usually it is one of three things. The model is answering an easier
          question, since predicting only "home win or not" turns three outcomes
          into two. Or it has been scored on a small, lucky run of matches. Or
          information from after the match has leaked into its inputs.
        </P>
        <P>
          Season to season variation is much larger than the difference between any
          two models, and it moves the market as well.
        </P>

        <div style={{ margin: `${space.xl}px 0` }}>
          <DataTable
            columns={[
              { key: "season", header: "Season", nowrap: true },
              { key: "model", header: "This model", numeric: true, render: (r) => `${r.model.toFixed(1)}%` },
              { key: "market", header: "Bookmakers", numeric: true, render: (r) => `${r.market.toFixed(1)}%` },
              { key: "alwaysHome", header: "Always home", numeric: true, render: (r) => `${r.alwaysHome.toFixed(1)}%` },
            ]}
            rows={BY_SEASON}
            rowKey={(r) => r.season}
          />
        </div>

        <P>
          When the model dropped ten points across two seasons it looked like
          something had broken. Nothing had. The market fell by almost exactly the
          same amount over the same period. 2025-26 was simply a stranger season
          than the two before it.
        </P>
      </Card>

      <Card style={CARD}>
        <SectionTitle level="primary" sub="One full holdout season, 380 matches">
          The draw problem
        </SectionTitle>

        <div style={{ margin: `${space.lg}px 0 ${space.xxl}px` }}>
          <OutcomeSplit />
        </div>

        <P>
          The model does not pick an outcome directly. It estimates how many goals
          each side will score, works out the chance of every possible scoreline,
          then reports which of the three results comes out on top.
        </P>
        <P>
          For a draw, both teams have to land on the same number. Add up every way
          that can happen, 0-0, 1-1, 2-2 and so on, and in a typical fixture it
          comes to about 26%. That is a reasonable estimate. Draws really do happen
          roughly a quarter of the time. But a strong home favourite will often sit
          at 55% or higher, so the draw ends up second most likely and almost never
          first.
        </P>

        <Aside label="The part that surprises people">
          Never naming a draw is not a flaw. It is what a well-calibrated
          forecaster does. The bookmakers' own prices behave the same way, and
          across thousands of matches the market almost never makes the draw its
          most likely single outcome.
        </Aside>
      </Card>

      <Card style={CARD}>
        <SectionTitle level="primary" sub="All six scored on the same holdout season">
          Five attempts to fix it
        </SectionTitle>
        <P>
          Two of the columns below are not accuracy, and they matter more. Log loss
          and RPS measure whether the probabilities are honest, so whether
          something given a 70% chance actually happens about 70% of the time. A
          model can pick more winners while being badly overconfident, and these
          two pick that up. Lower is better for both.
        </P>

        <div style={{ margin: `${space.xl}px 0` }}>
          <DataTable
            columns={[
              {
                key: "name", header: "Approach", minWidth: 240,
                render: (r) => (
                  <span>
                    {r.name}
                    {r.current && (
                      <span style={{
                        ...type.micro, marginLeft: 8, padding: "2px 6px", borderRadius: 4,
                        background: C.slate100, color: C.slate500,
                        textTransform: "uppercase", letterSpacing: "0.06em",
                      }}>
                        current
                      </span>
                    )}
                  </span>
                ),
              },
              { key: "correct", header: "Correct", numeric: true, render: (r) => `${r.correct.toFixed(1)}%` },
              { key: "logLoss", header: "Log loss", numeric: true, render: (r) => r.logLoss.toFixed(4) },
              { key: "rps", header: "RPS", numeric: true, render: (r) => r.rps.toFixed(4) },
              { key: "draws", header: "Draws called", numeric: true },
            ]}
            rows={ALTERNATIVES}
            rowKey={(r) => r.name}
            rowStyle={(r) => (r.current ? { background: C.slate50 } : null)}
          />
        </div>

        <P>
          Every alternative came out worse. The version built to predict results
          directly does call draws, fourteen of them, and is nearly three points
          less accurate for it, with noticeably worse probabilities. The standard
          statistical correction for this exact problem moved the result by 0.0001.
        </P>
        <P>
          So the most visible flaw in the model turns out to be the one thing worth
          leaving alone.
        </P>
      </Card>

      <Card style={CARD}>
        <SectionTitle level="primary">How to read a prediction</SectionTitle>
        <P>
          A prediction of "1-0" is not a claim that the match will finish 1-0. It
          is shorthand for the home side being more likely to win than not. The
          probabilities next to it carry the real information. A fixture at
          55/26/19 and one at 38/28/34 can both show as a home win, and they are
          saying very different things.
        </P>

        <Aside label="A fair test of any football model">
          Ask what it is being compared against. Always backing the home team gets
          you 43% for nothing, and the bookmakers get 54%. Anything claiming to sit
          well outside that range is worth a hard look at how it was measured.
        </Aside>

        <P>
          On that scale, 53.6% is a good result. It was never going to be a crystal
          ball. It is a reasonable estimate of something that stays largely
          uncertain, which is most of why people watch.
        </P>
      </Card>

      <div style={{
        ...type.micro, fontWeight: 400, color: C.slate400,
        maxWidth: "72ch", lineHeight: 1.7, marginTop: space.xl,
      }}>
        Figures measured in {MEASURED_ON} across three complete Premier League
        seasons. The bookmaker comparison uses published closing prices on the same
        fixtures. The alternative models were trained on 1,520 earlier matches and
        scored on a season none of them had seen. These are a snapshot from a
        specific study rather than live figures. The Dashboard and Model pages
        carry the current numbers.
      </div>
    </div>
  );
}

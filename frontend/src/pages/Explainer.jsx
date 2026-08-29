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
 * that bounds it is the bookmakers' 54.2% — and a visitor has no way to know that
 * unless the site says so. Every other page reports what the model did; this one
 * is the only place that says what a good answer would even look like.
 *
 * Deliberately static: see the note in explainerData.js. The Dashboard and Model
 * pages remain the live view.
 */
export default function Explainer() {
  return (
    <div style={{ maxWidth: 820 }}>
      <header style={{ marginBottom: space.xxl }}>
        <div style={{ ...type.micro, color: C.slate400, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: space.sm }}>
          Understanding the predictions
        </div>
        <h1 style={{ ...type.page, color: C.slate800, margin: 0, marginBottom: space.md }}>
          How good can a football model be?
        </h1>
        <div style={{ ...type.body, fontSize: 15, color: C.slate600, maxWidth: "62ch" }}>
          Almost everyone guesses too high. Here is the honest answer, measured over
          1,140 real Premier League matches &mdash; and what happened when five
          different approaches were tested against it.
        </div>
      </header>

      <Card style={{ marginBottom: space.xl }}>
        <SectionTitle level="primary" sub="Percentage of matches where the predicted result was correct, over the same 1,140 fixtures">
          Start with the benchmark that matters
        </SectionTitle>
        <P>
          A prediction model only means something next to something else. Against
          nothing, 53% sounds mediocre. So four forecasters were scored on exactly
          the same three seasons. One of them is the betting market&rsquo;s closing
          line &mdash; the price bookmakers settle on right before kick-off, after
          absorbing team news, injuries, suspensions and a great deal of informed
          money. It is the closest thing football has to a ceiling.
        </P>
        <div style={{ margin: `${space.xl}px 0` }}>
          <AccuracyLadder />
        </div>
        <Pull value="0.6" unit=" pts">
          The gap between this model and the entire global betting market. Not
          twenty points. Not ten. Six tenths of one.
        </Pull>
        <P>
          That reframes the question. The model is not failing to reach some
          obvious higher number &mdash; it has effectively caught up with the
          best-informed forecaster in the sport. What is left is not a modelling
          problem. It is football being genuinely unpredictable.
        </P>
      </Card>

      <Card style={{ marginBottom: space.xl }}>
        <SectionTitle level="primary">Why 60% is not on the table</SectionTitle>
        <P>
          If the bookmakers manage 54.2% with every advantage, a claim of 65% or
          70% is not ambition &mdash; it is a mistake somewhere in the
          measurement. Usually one of three: the model is answering an easier
          question (predicting only &ldquo;home win or not&rdquo; collapses three
          outcomes into two), it is measuring a lucky handful of matches, or
          information from after the match has leaked into its inputs.
        </P>
        <P>
          The honest caveat is that individual seasons swing far more than any
          model does &mdash; and they take the market with them.
        </P>
        <div style={{ margin: `${space.lg}px 0` }}>
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
          When the model dropped ten points across two seasons the instinct was
          that something had broken. Nothing had:{" "}
          <strong>the market dropped by almost exactly the same amount, at the same
          time.</strong> 2025-26 was simply a stranger season. A model&rsquo;s
          trend line means very little until a benchmark sits beside it.
        </P>
      </Card>

      <Card style={{ marginBottom: space.xl }}>
        <SectionTitle level="primary" sub="One full holdout season, 380 matches">
          The draw problem
        </SectionTitle>
        <div style={{ margin: `${space.lg}px 0` }}>
          <OutcomeSplit />
        </div>
        <P>
          The reason is worth understanding, because it is counter-intuitive. The
          model does not pick an outcome directly. It estimates{" "}
          <em>how many goals each side will score</em>, works out the chance of
          every possible scoreline, and reports which of the three results is most
          likely.
        </P>
        <P>
          A draw needs both teams to land on the same number. Add up every way
          that can happen &mdash; 0-0, 1-1, 2-2 and so on &mdash; and in a typical
          fixture it comes to roughly <strong>26%</strong>. That is a sensible
          estimate; draws really do happen about a quarter of the time. But a
          clear favourite at home often sits at <strong>55%</strong> or more. So
          the draw is frequently the second most likely outcome and almost never
          the first.
        </P>
        <Aside label="The part that surprises people">
          Never naming a draw is not a flaw. It is what a correctly calibrated
          forecaster does. The bookmakers&rsquo; own prices behave the same way
          &mdash; across thousands of matches, the market almost never makes the
          draw its single most likely outcome either.
        </Aside>
      </Card>

      <Card style={{ marginBottom: space.xl }}>
        <SectionTitle level="primary" sub="All six scored on the same holdout season; lower is better for log loss and RPS">
          So we tried to fix it. Five ways.
        </SectionTitle>
        <P>
          Two of these columns are not accuracy, and they matter more.{" "}
          <strong>Log loss</strong> and <strong>RPS</strong> measure whether the
          probabilities are honest &mdash; whether something given a 70% chance
          happens about 70% of the time. A model can pick more winners while being
          badly overconfident about them, and these catch that.
        </P>
        <div style={{ margin: `${space.lg}px 0` }}>
          <DataTable
            columns={[
              {
                key: "name", header: "Approach", minWidth: 230,
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
          <strong>Every alternative was worse.</strong> The model built to predict
          results directly does call draws &mdash; fourteen of them &mdash; and
          pays for it by being nearly three points less accurate, with noticeably
          worse probabilities. The textbook statistical correction for exactly
          this problem changed the result by 0.0001.
        </P>
        <P>
          Which leaves an unusual conclusion: the most visible flaw in the model
          is the one thing that should not be changed.
        </P>
      </Card>

      <Card style={{ marginBottom: space.xl }}>
        <SectionTitle level="primary">How to read a prediction</SectionTitle>
        <P>
          A prediction of &ldquo;1-0&rdquo; is not a claim that the match will
          finish 1-0. It is a compact way of saying the home side is more likely
          to win than not. The number worth reading is the probability beside it.
          A fixture at 55/26/19 and one at 38/28/34 may both display as a home
          win, and they are completely different statements.
        </P>
        <Aside label="A fair test of any football model">
          Ask what it is being compared against. Always picking the home team gets
          you <strong>43%</strong> for free, and the bookmakers get{" "}
          <strong>54%</strong>. Anything claiming to sit far outside that range
          deserves a hard look at how it was measured.
        </Aside>
        <P>
          Measured on that scale, a model at 53.6% is doing genuinely well. It is
          not a crystal ball and was never going to be one. It is a well-calibrated
          estimate of an event that remains, by its nature, mostly uncertain
          &mdash; which is exactly why people still watch the matches.
        </P>
      </Card>

      <div style={{ ...type.micro, fontWeight: 400, color: C.slate400, maxWidth: "70ch", lineHeight: 1.6 }}>
        Figures measured in {MEASURED_ON} over three complete Premier League
        seasons. The bookmaker comparison uses published closing prices on the
        same fixtures. Alternative models were trained on 1,520 earlier matches
        and scored on a season none of them had seen. These are a dated snapshot
        of a specific study, not live telemetry &mdash; the Dashboard and Model
        pages carry the current numbers.
      </div>
    </div>
  );
}

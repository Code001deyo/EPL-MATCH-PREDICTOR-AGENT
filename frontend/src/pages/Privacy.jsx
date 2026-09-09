import Masthead from "../components/Masthead";
import Card from "../components/ui/Card";
import { C } from "../theme";

/* The privacy policy.
 *
 * Written from what the code actually does, not from a template. Every claim
 * here is checkable against `backend/db/subscribers.py` (what is stored),
 * `backend/mailer.py` (where it goes) and `backend/routers/subscribe.py` (how it
 * is collected). A policy that describes a different system from the one running
 * is worse than none, because it is a promise nobody is keeping.
 *
 * If any of those files change, this page changes with them.
 */
export default function Privacy() {
  return (
    <>
      <Masthead title="Privacy">
        What this site collects, why, and how to get rid of it.
      </Masthead>

      <Card style={{ marginBottom: 20 }}>
        <Section title="The short version">
          <p style={p}>
            If you do not subscribe to match emails, this site collects nothing
            about you. No accounts, no advertising, no analytics scripts, no
            third-party trackers.
          </p>
          <p style={p}>
            If you do subscribe, we store your email address and nothing else
            about you.
          </p>
        </Section>
      </Card>

      <Card style={{ marginBottom: 20 }}>
        <Section title="What is stored when you subscribe">
          <ul style={list}>
            <li><strong>Your email address</strong>, lower-cased.</li>
            <li>
              <strong>Two random tokens</strong>: one to confirm the address, one
              to unsubscribe. They are how a link in an email proves it came from
              us without you needing a password.
            </li>
            <li>
              <strong>Three timestamps</strong>: when you subscribed, when you
              confirmed, and when you unsubscribed if you have.
            </li>
            <li>
              <strong>A record of which emails were sent to you</strong>, as a
              fixture id and whether it was the pre-match or post-match message.
              This exists so a retry cannot send you the same email twice.
            </li>
          </ul>
          <p style={p}>
            No name, no IP address, no location, no device information, no
            behavioural profile. There is nothing else to store because nothing
            else is asked for.
          </p>
        </Section>
      </Card>

      <Card style={{ marginBottom: 20 }}>
        <Section title="Confirmation is required">
          <p style={p}>
            Typing an address into the form does not subscribe it. Nothing is sent
            until you open the confirmation link we email you. This is deliberate:
            it means nobody can sign someone else up.
          </p>
        </Section>
      </Card>

      <Card style={{ marginBottom: 20 }}>
        <Section title="Who else sees it">
          <p style={p}>
            One company. Emails are delivered by{" "}
            <a href="https://resend.com/legal/privacy-policy" style={link}
               target="_blank" rel="noopener noreferrer">Resend</a>, which
            processes your address in order to deliver the message. It is not sold,
            rented, shared for advertising, or passed to anyone else.
          </p>
          <p style={p}>
            Match data on this site comes from the Premier League's public feed and
            from football-data.co.uk. That is data about football, not about you,
            and it flows in the opposite direction.
          </p>
        </Section>
      </Card>

      <Card style={{ marginBottom: 20 }}>
        <Section title="Leaving, and deletion">
          <p style={p}>
            Every email carries an unsubscribe link. It works in one click, needs
            no login, and takes effect immediately.
          </p>
          <p style={p}>
            Being straight about what unsubscribing does: your address is marked as
            unsubscribed and stops receiving anything, but the row is kept so that
            a later bulk import could not quietly re-add you. If you would rather
            it were erased completely, ask and it will be, along with the record of
            what was sent to you.
          </p>
        </Section>
      </Card>

      <Card style={{ marginBottom: 20 }}>
        <Section title="Cookies">
          <p style={p}>
            None for visitors. The site sets no cookies, and the only browser
            storage it uses is for its own interface state, which never leaves your
            device.
          </p>
          <p style={p}>
            A session cookie exists for the operator sign-in, which is not
            available to visitors and is not set unless somebody signs in.
          </p>
        </Section>
      </Card>

      <Card>
        <Section title="Contact">
          <p style={p}>
            This site is operated by Hanova Technologies. For anything on this page,
            including a request to erase your address, write to{" "}
            <a href="mailto:privacy@hanovatechnologies.co.ke" style={link}>
              privacy@hanovatechnologies.co.ke
            </a>.
          </p>
          <p style={{ ...p, color: C.slate400, fontSize: 12 }}>
            Predictions on this site are a statistical model's output, published for
            interest. They are not betting advice.
          </p>
        </Section>
      </Card>
    </>
  );
}

function Section({ title, children }) {
  return (
    <>
      <h2 style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 700, color: C.slate800 }}>
        {title}
      </h2>
      {children}
    </>
  );
}

const p = { margin: "0 0 10px", fontSize: 13, lineHeight: 1.7, color: C.slate600, maxWidth: "68ch" };
const list = { margin: "0 0 10px", paddingLeft: 18, fontSize: 13, lineHeight: 1.8, color: C.slate600, maxWidth: "68ch" };
const link = { color: C.blueDark, fontWeight: 600 };

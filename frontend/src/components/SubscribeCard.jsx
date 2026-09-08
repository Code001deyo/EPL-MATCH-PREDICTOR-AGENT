import { useEffect, useState } from "react";
import axios from "axios";
import API from "../config";

/* Sign up for match notifications.
 *
 * Two things this deliberately does not do.
 *
 * It does not promise "10 minutes before kickoff". The dispatcher is driven by a
 * five-minute cron on free infrastructure, which drifts; the honest claim is
 * "before kickoff", and that is what it says. Promising a precision the system
 * cannot hold would be a lie that arrives late, in an inbox, repeatedly.
 *
 * It does not report whether an address is already subscribed. The API answers
 * the same generic body for every outcome so it cannot be used to test who is
 * subscribed, and echoing anything more specific here would undo that.
 */
export default function SubscribeCard() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle");    // idle | sending | sent | error
  const [status, setStatus] = useState(null);

  useEffect(() => {
    let live = true;
    axios
      .get(`${API}/subscribe/status`)
      .then(({ data }) => live && setStatus(data))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (!email.trim() || state === "sending") return;

    setState("sending");
    try {
      await axios.post(`${API}/subscribe`, { email: email.trim() });
      setState("sent");
      setEmail("");
    } catch {
      setState("error");
    }
  }

  // If the server has no mailer configured, saying so beats a form that accepts
  // an address and silently never delivers.
  const undeliverable = status && status.delivery_configured === false;

  return (
    <section className="pl-subscribe" aria-labelledby="subscribe-heading">
      <h2 id="subscribe-heading">Get every prediction by email</h2>
      <p>
        The model's call on each fixture shortly before kickoff, then the result
        and how that call went shortly after the final whistle. Two emails per
        match, and every one of them has an unsubscribe link.
      </p>

      {state === "sent" ? (
        <p style={{ margin: 0, fontWeight: 600, color: "#00ff85" }} role="status">
          Check your inbox — open the confirmation link and you're subscribed.
          Nothing is sent until you do.
        </p>
      ) : (
        <form className="pl-subscribe-form" onSubmit={submit}>
          <label htmlFor="subscribe-email" className="pl-sr-only">
            Email address
          </label>
          <input
            id="subscribe-email"
            type="email"
            required
            value={email}
            placeholder="you@example.com"
            onChange={(e) => setEmail(e.target.value)}
            disabled={undeliverable}
          />
          <button type="submit" disabled={state === "sending" || undeliverable}>
            {state === "sending" ? "Sending…" : "Subscribe"}
          </button>
        </form>
      )}

      {state === "error" && (
        <p className="pl-subscribe-note" role="alert" style={{ color: "#fca5a5" }}>
          That didn't go through. Try again in a moment.
        </p>
      )}

      {undeliverable && (
        <p className="pl-subscribe-note" role="status">
          Email delivery isn't configured on this instance yet, so sign-ups are
          closed rather than silently going nowhere.
        </p>
      )}

      <p className="pl-subscribe-note">
        {/* The timing caveat, stated where someone is deciding to sign up rather
            than buried in a policy page. */}
        Emails go out in a window before kickoff, not at an exact minute — the
        scheduler runs every five minutes and free infrastructure drifts.
        {status?.confirmed > 0 && ` ${status.confirmed} subscribed.`}
      </p>
    </section>
  );
}

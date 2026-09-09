import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import Card from "../ui/Card";
import SectionTitle from "../ui/SectionTitle";
import { C, radius, semantic, space, type } from "../../theme";
import { API } from "../../config";

/* Who is on the list, and the two things an operator may do about it.
 *
 * This is the only screen in the app that shows email addresses, which is why it
 * lives behind the operator sign-in and why the public counterpart,
 * /subscribe/status, returns a count and nothing else.
 *
 * Two actions, deliberately different:
 *
 *   Unsubscribe  stops sending and keeps the row as a suppression record, so a
 *                later import cannot quietly put the address back.
 *   Erase        removes the address and the record of what was sent to it. The
 *                privacy policy offers this on request, so it needs to be
 *                something a person can actually carry out.
 *
 * Erase is the destructive one and asks first. Unsubscribe does not: it is
 * reversible from the row next to it.
 */
export default function SubscriberList() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [confirming, setConfirming] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/admin/subscribers`);
      setData(data);
      setError(null);
    } catch {
      setError("Could not load the subscriber list.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function act(id, path, method = "post") {
    setBusy(id);
    try {
      await axios[method](`${API}/admin/subscribers/${id}${path}`);
      await load();
      setConfirming(null);
    } catch {
      setError("That did not go through. The list below may be out of date.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <SectionTitle
        sub={
          data
            ? `${data.active} active · ${data.pending} awaiting confirmation · ${data.total} total`
            : "Loading"
        }
      >
        Subscribers
      </SectionTitle>

      {error && (
        <div style={{ ...type.body, color: C.rose, marginBottom: space.md }}>{error}</div>
      )}

      {data && data.subscribers.length === 0 && (
        <div style={{ ...type.body, color: C.slate400 }}>
          Nobody has subscribed yet.
        </div>
      )}

      {data && data.subscribers.length > 0 && (
        <div className="pl-scroll-x">
          {/* pl-stack-table: below 720px each row becomes a block with its column
              name as a label, using the data-label on every cell. Without it the
              five columns scroll sideways inside .pl-scroll-x and an operator on
              a phone has to drag the table right to reach Unsubscribe and Erase.
              The treatment already existed in the stylesheet and nothing had
              used it. */}
          <table className="pl-table pl-stack-table">
            <thead>
              <tr>
                <th scope="col">Address</th>
                <th scope="col">State</th>
                <th className="pl-num" scope="col">Emails</th>
                <th scope="col">Since</th>
                <th scope="col" style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.subscribers.map((s) => (
                <tr key={s.id}>
                  <td data-label="Address" style={{ fontWeight: 600, color: C.slate800 }}>
                    {s.email}
                  </td>
                  <td data-label="State"><StateBadge state={s.state} /></td>
                  <td className="pl-num" data-label="Emails">{s.emails_sent}</td>
                  <td data-label="Since" style={{ color: C.slate500, whiteSpace: "nowrap" }}>
                    {(s.created_at || "").slice(0, 10) || "-"}
                  </td>
                  <td data-label="Actions" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {confirming === s.id ? (
                      <>
                        <span style={{ ...type.micro, color: C.slate600, marginRight: 8 }}>
                          Erase {s.email} and everything sent to them?
                        </span>
                        <Action
                          label="Erase"
                          danger
                          busy={busy === s.id}
                          onClick={() => act(s.id, "", "delete")}
                        />
                        <Action label="Cancel" onClick={() => setConfirming(null)} />
                      </>
                    ) : (
                      <>
                        {s.state === "unsubscribed" ? (
                          <Action
                            label="Resubscribe"
                            busy={busy === s.id}
                            onClick={() => act(s.id, "/resubscribe")}
                          />
                        ) : (
                          <Action
                            label="Unsubscribe"
                            busy={busy === s.id}
                            onClick={() => act(s.id, "/unsubscribe")}
                          />
                        )}
                        <Action label="Erase" danger onClick={() => setConfirming(s.id)} />
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="pl-caveat">
        Unsubscribing keeps the address as a suppression record, so it cannot be
        added back by a later import. Erasing removes it and the record of what
        was sent to it, which is what the privacy policy offers on request.
        Resubscribing only undoes an unsubscribe: an address that never confirmed
        stays pending, because consent is not an operator's to give.
      </p>
    </Card>
  );
}

function StateBadge({ state }) {
  const palette = {
    active: { bg: "#e7f5ee", color: C.emerald },
    pending: { bg: "#fbf1e2", color: semantic.warn },
    unsubscribed: { bg: C.slate100, color: C.slate500 },
  }[state] || { bg: C.slate100, color: C.slate500 };

  return (
    <span style={{
      ...type.micro, padding: "3px 8px", borderRadius: 999,
      background: palette.bg, color: palette.color, whiteSpace: "nowrap",
    }}>
      {state}
    </span>
  );
}

function Action({ label, onClick, busy, danger }) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      style={{
        marginLeft: 6, padding: "5px 10px", borderRadius: radius.sm,
        border: `1px solid ${danger ? "#f0bfcd" : C.slate200}`,
        background: C.white, color: danger ? C.rose : C.slate600,
        ...type.micro, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1,
      }}
    >
      {busy ? "..." : label}
    </button>
  );
}

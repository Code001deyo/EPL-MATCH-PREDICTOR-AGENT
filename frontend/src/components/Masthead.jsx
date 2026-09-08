import { useEffect, useState } from "react";
import axios from "axios";
import API from "../config";

/* The page header, in Premier League house style.
 *
 * Carries the season, the matchweek and when the data was last refreshed. That
 * last one is not decoration: this site is only as current as its last refresh,
 * and for eleven days the scheduled refresh was failing while every page looked
 * exactly as it always had. A visible timestamp is the cheapest way for a stale
 * instance to admit it.
 */
export default function Masthead({ title, children }) {
  const [freshness, setFreshness] = useState(null);

  useEffect(() => {
    let live = true;
    axios
      .get(`${API}/data/freshness`)
      .then(({ data }) => live && setFreshness(data))
      // Silent: a missing timestamp shows nothing rather than an error banner
      // above every page. The absence is itself the signal.
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  return (
    <header className="pl-masthead">
      <h1>{title}</h1>
      {children && <p>{children}</p>}

      <div className="pl-masthead-meta">
        {freshness?.current_season && (
          <span>
            Season <strong>{freshness.current_season}</strong>
          </span>
        )}
        {typeof freshness?.matches_played === "number" && (
          <span>
            <strong>{freshness.matches_played}</strong> matches played
          </span>
        )}
        {freshness?.last_refreshed && (
          <span>
            Data updated <strong>{relative(freshness.last_refreshed)}</strong>
          </span>
        )}
      </div>
    </header>
  );
}

/* "3 hours ago" rather than an ISO string: the question a reader is asking is
 * how stale this is, not what the clock said. */
function relative(iso) {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "unknown";

  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;

  const days = Math.round(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}

import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../config";

/* Shared access to GET /model/backtest.
 *
 * Three panels on the dashboard read this payload — the accuracy trend, the
 * season comparison and calibration — and each mounting its own request would
 * fire three identical calls for one response. The in-flight promise is cached
 * at module scope so they share a single round trip.
 *
 * `refresh()` clears the cache, which is what the calibration panel needs after
 * it triggers a new backtest run: without it the other panels would keep showing
 * the previous result until a full page reload. */
let cached = null;

function fetchBacktest() {
  if (!cached) {
    cached = axios.get(`${API}/model/backtest`).then(
      (r) => ({ data: r.data, status: "ready" }),
      (e) => {
        // A 404 means the endpoint isn't there; anything else is a real failure.
        // They are different states and the panels render them differently.
        cached = null;   // don't cache a failure — a retry should actually retry
        return { data: null, status: e?.response?.status === 404 ? "not-measured" : "error" };
      }
    );
  }
  return cached;
}

export function invalidateBacktest() {
  cached = null;
}

export default function useBacktest() {
  const [state, setState] = useState({ status: "loading", data: null });

  useEffect(() => {
    let cancelled = false;
    fetchBacktest().then((r) => { if (!cancelled) setState(r); });
    return () => { cancelled = true; };
  }, []);

  return state;
}

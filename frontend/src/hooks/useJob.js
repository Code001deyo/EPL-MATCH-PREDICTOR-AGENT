import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";

const POLL_MS = 2000;

/* Track a server-side background job from start to finish.
 *
 * Retraining, backtesting and refreshing are all jobs now, for the same reason:
 * each runs longer than the browser — and the CDN in front of it — will hold an
 * idle connection open. Fired as a plain blocking POST they reported failure for
 * work that was still running and finished fine, and the operator had no way to
 * learn how it ended.
 *
 * The server answers 202 with a job id immediately; this polls it. Because the
 * job lives on the server, a reload or a closed tab loses the polling, not the
 * work — `attach` re-joins whatever is still in flight.
 */
export default function useJob(jobUrl) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => stop, [stop]);

  const attach = useCallback((id) => {
    stop();
    timer.current = setInterval(async () => {
      try {
        const { data } = await axios.get(jobUrl(id));
        setJob(data);
        if (data.state !== "running") stop();
      } catch (e) {
        // A polling blip is not a failed job. The work is server-side and keeps
        // going; say that rather than declaring a failure that did not happen.
        setError("Lost contact while polling; the job may still be running.");
      }
    }, POLL_MS);
  }, [jobUrl, stop]);

  const start = useCallback(async (request) => {
    setError(null);
    setJob(null);
    try {
      const { data } = await request();
      if (data?.job) setJob(data.job);
      if (data?.job_id) attach(data.job_id);
      return data;
    } catch (err) {
      // 401 and 409 mean the server refused with a reason; a missing response
      // means the network failed. They are not the same problem.
      setError(
        err?.response?.status === 401
          ? "Your session expired — sign in again."
          : err?.response?.data?.detail
            || (err?.response ? `Rejected (HTTP ${err.response.status}).` : "Could not reach the backend.")
      );
      return null;
    }
  }, [attach]);

  return {
    job,
    error,
    start,
    attach,
    running: job?.state === "running",
  };
}

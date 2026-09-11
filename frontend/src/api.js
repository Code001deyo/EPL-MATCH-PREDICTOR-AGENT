import axios from "axios";

/* A 200 that is not JSON is a failure, and has to be treated as one.
 *
 * Every call in this app reads a named field off the body - `r.data.teams`,
 * `r.data.predictions`, `r.data.seasons` - and every one of them is wrapped in a
 * `.catch` that leaves the page in its empty state. That is the right shape, and
 * it only works while a broken response actually rejects.
 *
 * It did not. When something answers `/api/teams` with the app's own
 * `index.html` and a 200, axios resolves, `r.data` is a string of HTML,
 * `r.data.teams` is `undefined`, and the page stores `undefined` where it had an
 * array. Nothing throws until the render reaches `teams.map` - so the failure
 * surfaces as a blank white page with `Cannot read properties of undefined` in
 * the console, several steps from the request that caused it.
 *
 * This is not hypothetical. It is exactly what a misconfigured rewrite does: the
 * SPA fallback in `vercel.json` catches `/api` and serves the shell instead of
 * proxying to the backend. Teams, Analytics and History all white-screened this
 * way, and the QA sweep caught it because the pages rendered zero characters.
 *
 * So the check goes here, once, rather than at each of the thirty-odd call
 * sites. An interceptor on the default axios instance covers every one of them,
 * including the ones added tomorrow.
 */

/* An empty body is legitimate - 204 and 205 say so by definition, and a plain
 * 200 with nothing in it is not this bug. Only a body that claims to be
 * something other than JSON, or that arrived as raw text because axios could not
 * parse it, is. */
export function jsonProblem(response) {
  const status = response.status;
  if (status === 204 || status === 205) return null;

  const type = String(response.headers?.["content-type"] || "");
  if (type && !type.includes("json")) {
    return `expected JSON, got ${type.split(";")[0].trim()}`;
  }

  // axios leaves the body as a string when it is not parseable JSON. A response
  // that really is a JSON string is not something this API returns.
  if (typeof response.data === "string" && response.data.trim() !== "") {
    return "expected JSON, got an unparsed body";
  }

  return null;
}

axios.interceptors.response.use((response) => {
  const problem = jsonProblem(response);
  if (!problem) return response;

  const error = new Error(
    `${response.config?.url || "request"}: ${problem}. ` +
    "The API is probably not reachable and something else answered - check the " +
    "/api rewrite."
  );
  error.response = response;
  error.isJsonContractError = true;
  return Promise.reject(error);
});

export default axios;

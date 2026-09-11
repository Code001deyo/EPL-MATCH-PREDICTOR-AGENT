import { jsonProblem } from "./api";

/* The case these exist for: the SPA fallback answered /api with index.html and a
 * 200, three pages stored `undefined` where they had arrays, and the first
 * `.map` in the render threw. The interceptor turns that into a rejection so the
 * `.catch` each page already has does its job. */

const res = (over = {}) => ({
  status: 200,
  headers: { "content-type": "application/json" },
  data: { teams: ["Arsenal"] },
  ...over,
});

describe("jsonProblem", () => {
  it("passes a normal JSON response", () => {
    expect(jsonProblem(res())).toBeNull();
  });

  it("rejects the app shell served in place of the API", () => {
    const problem = jsonProblem(res({
      headers: { "content-type": "text/html; charset=utf-8" },
      data: "<!doctype html><html lang=\"en\"><head>",
    }));
    expect(problem).toMatch(/text\/html/);
  });

  it("rejects a body axios could not parse, whatever the header claims", () => {
    // A server can send application/json and a body that is not. The header is
    // a claim; the body is the evidence.
    expect(jsonProblem(res({ data: "<!doctype html>" }))).toMatch(/unparsed/);
  });

  it("allows an empty body on 204", () => {
    expect(jsonProblem(res({ status: 204, headers: {}, data: "" }))).toBeNull();
  });

  it("allows a 200 with an empty body", () => {
    expect(jsonProblem(res({ data: "" }))).toBeNull();
  });

  it("allows a missing content-type when the body parsed", () => {
    expect(jsonProblem(res({ headers: {} }))).toBeNull();
  });

  it("allows an array body", () => {
    expect(jsonProblem(res({ data: [1, 2, 3] }))).toBeNull();
  });
});

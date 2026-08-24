# Frontend deployment (Vercel)

`vercel.json` does the same job nginx does locally, and deliberately so.

## The rewrite is the whole design

```
/api/:path*  ->  https://<space>.hf.space/:path*
```

Vercel proxies this **server-side**, so the browser only ever talks to one origin.
That means:

- `REACT_APP_API_BASE` stays at its `/api` default. Nothing host-specific is
  compiled into the bundle, so the same build works from any URL. Baking
  `http://localhost:8001` into the bundle is the bug this architecture exists to
  prevent — it fails silently, with the page loading and the data never arriving.
- No CORS configuration, no preflight, no `allow_origins` to widen.
- Local development through nginx and production through Vercel exercise the
  **same code path**. A production-only code path is an untested one.

The second rewrite is the SPA fallback — every non-`/api` path serves
`index.html` so client-side routes survive a hard refresh. The negative lookahead
matters: without it the fallback would swallow the API proxy.

## Setup

1. Import the GitHub repo into Vercel.
2. Set **Root Directory** to `frontend`. Everything else is inferred.
3. Replace `REPLACE-ME` in `vercel.json` with the real Space host
   (`owner/space-name` becomes `owner-space-name.hf.space`, lowercased) and push.

Vercel's own GitHub integration builds on every push to `main`, so no workflow is
needed here — the file and the connection are the entire configuration.

## The limit that will actually be hit

Vercel's proxy has an edge response timeout in the tens of seconds. Nothing the UI
calls exceeds it today because retraining is asynchronous — `POST /model/retrain`
returns `202` with a job id in ~0.2s and the browser polls `/model/jobs/{id}`.
A **synchronous** long endpoint added later would time out at the proxy while
succeeding on the backend, which is exactly how retrain used to report
"Retrain failed" after a successful 321-second run. Keep long work behind the job
API.

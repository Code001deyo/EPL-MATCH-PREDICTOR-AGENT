"""Concurrency probe for POST /predict.

Answers one question with numbers: what happens when N people predict at once?

    python scripts/loadtest.py http://localhost:3000/api 10
    python scripts/loadtest.py https://your-api.onrender.com 10

Kept in the repo because the fix it verifies is easy to regress. Measured on this
project:

    before  10 concurrent -> 0/10 succeeded, all HTTP 500
                             sqlite3.OperationalError: database is locked
            single request -> 4.56s

    after   10 concurrent -> 10/10 succeeded in 4.30s wall clock
            single request -> 0.84s

The three changes behind that: SQLite in WAL mode with a busy timeout, the twelve
trained models cached in memory instead of re-read from disk every request, and
the match frame cached instead of rebuilt from 6,545 ORM rows per call.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000/api"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 10

PAIRS = [
    ("Arsenal", "Chelsea"), ("Liverpool", "Man City"), ("Everton", "Spurs"),
    ("Brighton", "Newcastle"), ("Fulham", "Brentford"), ("Leeds", "Sunderland"),
    ("Man Utd", "Aston Villa"), ("Bournemouth", "Crystal Palace"),
    ("Ipswich", "Nott'm Forest"), ("Coventry", "Hull"),
]


def one(i):
    home, away = PAIRS[i % len(PAIRS)]
    body = json.dumps({"home_team": home, "away_team": away}).encode()
    req = urllib.request.Request(
        f"{BASE}/predict", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            r.read()
            return ("ok", r.status, time.time() - t0)
    except urllib.error.HTTPError as e:
        return ("http_error", e.code, time.time() - t0)
    except Exception as e:
        return (type(e).__name__, 0, time.time() - t0)


# Warm one request so the comparison is against a warm process, not a cold one.
kind, code, warm = one(0)
print(f"  single warm request: {warm:.2f}s  ({kind} {code})")

t0 = time.time()
with ThreadPoolExecutor(max_workers=N) as pool:
    results = list(pool.map(one, range(N)))
wall = time.time() - t0

ok = [r for r in results if r[0] == "ok"]
bad = [r for r in results if r[0] != "ok"]
lat = sorted(r[2] for r in results)

print(f"\n  {N} concurrent POST /predict")
print(f"    wall clock      : {wall:.2f}s")
print(f"    succeeded       : {len(ok)}/{N}")
if bad:
    print(f"    FAILED          : {len(bad)} -> {sorted({(b[0], b[1]) for b in bad})}")
if lat:
    print(f"    latency min/med/max : {lat[0]:.2f}s / {lat[len(lat)//2]:.2f}s / {lat[-1]:.2f}s")
    print(f"    slowdown vs single  : {lat[-1]/warm:.1f}x on the worst request")
